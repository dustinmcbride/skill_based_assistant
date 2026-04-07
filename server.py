import base64
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure assistant/ is on sys.path when running via uvicorn from project root
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

import agent
import memory
from skills.notes.obsidian import _vault_path as _obsidian_vault_path
from skills.trello.trello import _compact_overview, _get_cache
from skills.process_email.agentmail import get_email_thread
from skills.telegram import send_message as telegram_send
from user_context import load_user_context, load_user_context_by_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
_TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _TELEGRAM_BOT_TOKEN and _TELEGRAM_WEBHOOK_URL:
        url = f"https://api.telegram.org/bot{_TELEGRAM_BOT_TOKEN}/setWebhook"
        payload: dict = {"url": _TELEGRAM_WEBHOOK_URL}
        if _TELEGRAM_WEBHOOK_SECRET:
            payload["secret_token"] = _TELEGRAM_WEBHOOK_SECRET
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
        if resp.is_success:
            logger.info("Telegram webhook registered: %s", _TELEGRAM_WEBHOOK_URL)
        else:
            logger.warning("Telegram webhook registration failed: %s %s", resp.status_code, resp.text)
    else:
        logger.info("Telegram webhook not registered (TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_URL not set)")

    import skills as _skills
    tools = _skills.get_tools()
    logger.info("Skills loaded at boot: %s", [t["name"] for t in tools])

    yield


app = FastAPI(title="Personal Assistant", lifespan=lifespan)

# Dedup Telegram updates by update_id — keeps last 1000 to bound memory
_SEEN_UPDATE_IDS: collections.OrderedDict = collections.OrderedDict()
_MAX_SEEN_UPDATES = 1000

_CAPTURE_API_KEY = os.environ.get("CAPTURE_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key")

_SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
_SLACK_TOLERANCE_SECONDS = 300
_SEEN_SLACK_EVENT_IDS: collections.OrderedDict = collections.OrderedDict()
_MAX_SEEN_SLACK_EVENTS = 1000


def _require_api_key(api_key: str = Security(_api_key_header)) -> None:
    if not _CAPTURE_API_KEY or not hmac.compare_digest(api_key, _CAPTURE_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


_WEBHOOK_SECRET = os.environ.get("AGENTMAIL_WEBHOOK_SECRET", "")
_WEBHOOK_TOLERANCE_SECONDS = 300


def _verify_signature(secret: str, svix_id: str, svix_timestamp: str, svix_signature: str, body: bytes) -> bool:
    """Verify Svix v1 webhook signature."""
    try:
        ts = int(svix_timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > _WEBHOOK_TOLERANCE_SECONDS:
        return False

    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    raw_secret = base64.b64decode(secret.removeprefix("whsec_"))
    expected = base64.b64encode(
        hmac.new(raw_secret, signed_content, hashlib.sha256).digest()
    ).decode()

    for part in svix_signature.split():
        if part.startswith("v1,") and hmac.compare_digest(part[3:], expected):
            return True
    return False



@app.get("/health")
async def health():
    return {"status": "ok"}


_OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "obsidian_vault")).expanduser()
if not _OBSIDIAN_VAULT.is_absolute():
    _OBSIDIAN_VAULT = Path(__file__).parent / _OBSIDIAN_VAULT
_INBOX_PATH = _OBSIDIAN_VAULT / "Inbox.md"


def _trello_context() -> str:
    """Return compact Trello overview for agent context injection. Returns empty string on any error."""
    try:
        cache = _get_cache()
        overview = _compact_overview(cache)
        fetched_at = cache.get("fetched_at", "")[:19].replace("T", " ")
        return f"## Trello Boards & Lists (as of {fetched_at} UTC)\n{overview}"
    except Exception:
        return ""


def _capture_context() -> str:
    """Return a pre-fetched Trello overview and Obsidian file list for the capture prompt."""
    lines = []

    trello_ctx = _trello_context()
    lines.append(trello_ctx if trello_ctx else "## Trello Boards & Lists\n(unavailable)")

    lines.append("\n\n## Obsidian Vault Files\n")
    try:
        vault = _obsidian_vault_path()
        if vault.exists():
            files = sorted(p.name for p in vault.rglob("*.md"))
            lines.append("\n".join(files) if files else "(vault is empty)")
        else:
            lines.append("(vault not found)")
    except Exception as e:
        lines.append(f"(unavailable: {e})")

    return "\n".join(lines)


def _append_to_inbox(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _INBOX_PATH.open("a") as f:
        f.write(f"\n## {timestamp}\n\n{message}\n")


class CaptureRequest(BaseModel):
    message: str


@app.post("/capture/{username}", status_code=200)
async def capture(username: str, body: CaptureRequest, background_tasks: BackgroundTasks, _: None = Security(_require_api_key)):
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    _INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _INBOX_PATH.open("a") as f:
        f.write(f"- [{now}] {body.message}\n")
    logger.info("Capture inbox entry: %s", body.message[:200])

    try:
        user = load_user_context_by_id(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        context = _capture_context()
    except Exception as e:
        logger.warning("Failed to build capture context: %s", e)
        context = ""

    capture_prompt = (
        f"File this captured note: {body.message}\n\n"
        f"IMPORTANT: Do NOT read Inbox.md. It is an append-only log — the note has already been "
        f"appended there. Only take action if the note should be filed somewhere else "
        f"(e.g. a shopping list, a specific note, a todo). Otherwise just confirm it was captured."
    )
    if context:
        capture_prompt += f"\n\n---\n\n{context}"

    def _run_capture():
        hist = [{"role": "user", "content": capture_prompt}]
        try:
            response_text, _, _ = agent.run(hist, user=user, mode="command")
            logger.info("Capture agent response: %s", response_text[:500] if response_text else "(empty)")
            telegram_chat_id = user.channels.get("telegram", "")
            if response_text and telegram_chat_id:
                ok = telegram_send(telegram_chat_id, response_text)
                logger.info("Capture telegram send to %s: %s", telegram_chat_id, "ok" if ok else "failed")
            else:
                logger.warning("Capture: no telegram channel for user %s or empty response", username)
        except Exception:
            logger.exception("Capture agent error for user %s", username)

    background_tasks.add_task(_run_capture)
    return {"status": "received"}




@app.post("/webhook/email")
async def webhook_email(request: Request):
    body = await request.body()

    if _WEBHOOK_SECRET:
        svix_id = request.headers.get("svix-id", "")
        svix_timestamp = request.headers.get("svix-timestamp", "")
        svix_signature = request.headers.get("svix-signature", "")
        if not _verify_signature(_WEBHOOK_SECRET, svix_id, svix_timestamp, svix_signature, body):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json() if not body else __import__("json").loads(body)
    event_type = payload.get("event_type", "") or payload.get("type", "")
    logger.info("Webhook received: event_type=%r payload_keys=%s", event_type, list(payload.keys()))

    if event_type != "message.received":
        logger.info("Webhook ignored: event_type=%r (not message.received)", event_type)
        return {"status": "ignored", "type": event_type}

    data = payload.get("message", payload.get("data", {}))
    thread = payload.get("thread", {})
    sender = data.get("from", "unknown")
    subject = data.get("subject") or thread.get("subject", "(no subject)")
    thread_id = data.get("thread_id") or thread.get("thread_id") or thread.get("id", "")
    logger.info("Webhook email: from=%r subject=%r thread_id=%r data_keys=%s thread_keys=%s", sender, subject, thread_id, list(data.keys()), list(thread.keys()))

    if not thread_id:
        logger.warning("Webhook payload missing thread_id, skipping")
        return {"status": "ignored", "reason": "missing thread_id"}

    logger.info("Fetching thread %r from AgentMail", thread_id)
    thread_content = get_email_thread(thread_id)
    logger.info("Thread fetch complete: %d chars", len(thread_content))

    message = (
        f"New email received — from: {sender}, subject: {subject}.\n\n"
        f"Full thread:\n\n{thread_content}\n\n"
        f"File any travel/trip information you find."
    )

    hist = [{"role": "user", "content": message}]

    logger.info("Running agent for webhook email thread_id=%r", thread_id)
    try:
        _, skill_name, actions_taken = agent.run(hist, user=None, mode="command")
    except Exception as e:
        logger.exception("Agent loop error processing webhook")
        return {"status": "error", "detail": str(e)}
    logger.info("Webhook processed: skill=%s actions=%s", skill_name, actions_taken)
    return {"status": "ok", "skill": skill_name, "actions_taken": actions_taken}


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    if _TELEGRAM_WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(token, _TELEGRAM_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid secret token")

    payload = await request.json()

    update_id = payload.get("update_id")
    if update_id is not None:
        if update_id in _SEEN_UPDATE_IDS:
            logger.info("Telegram duplicate update_id=%s, ignoring", update_id)
            return {"status": "ignored", "reason": "duplicate"}
        _SEEN_UPDATE_IDS[update_id] = True
        if len(_SEEN_UPDATE_IDS) > _MAX_SEEN_UPDATES:
            _SEEN_UPDATE_IDS.popitem(last=False)

    message = payload.get("message") or payload.get("edited_message", {})
    if not message:
        return {"status": "ignored", "reason": "no message"}

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return {"status": "ignored", "reason": "missing chat_id or text"}

    logger.info("Telegram message: chat_id=%r text=%r", chat_id, text[:200])

    user = load_user_context("telegram", chat_id)
    if user.is_anonymous:
        logger.info("Anonymous Telegram user: chat_id=%r, assigned user_id=%r", chat_id, user.user_id)

    hist = memory.load(user)
    trello_ctx = _trello_context()
    enriched = f"{trello_ctx}\n\n---\n\n{text}" if trello_ctx else text
    agent_hist = list(hist)
    agent_hist.append({"role": "user", "content": enriched})

    try:
        response_text, skill_name, actions_taken = agent.run(agent_hist, user=user, mode="command")
    except Exception as e:
        logger.exception("Agent loop error for Telegram user %s", user.user_id)
        telegram_send(chat_id, "Sorry, something went wrong.")
        return {"status": "error", "detail": str(e)}

    hist.append({"role": "user", "content": text})
    hist.append({"role": "assistant", "content": response_text})
    memory.save(hist, user)

    if response_text:
        telegram_send(chat_id, response_text)

    logger.info("Telegram reply sent: skill=%s actions=%s", skill_name, actions_taken)
    return {"status": "ok", "skill": skill_name, "actions_taken": actions_taken}


def _verify_slack_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Verify Slack request signature (v0 scheme)."""
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > _SLACK_TOLERANCE_SECONDS:
        return False
    basestring = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/slack")
async def webhook_slack(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    if _SLACK_SIGNING_SECRET:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not _verify_slack_signature(_SLACK_SIGNING_SECRET, timestamp, body, signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = json.loads(body)

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    event_type = event.get("type", "")
    channel = event.get("channel", "")

    from skills.slack import bot_participated_in_thread, get_bot_user_id
    bot_id = get_bot_user_id()

    # Never respond to our own messages or Slack system subtypes (edits, deletions, etc.)
    if event.get("bot_id") or event.get("subtype") or (bot_id and event.get("user") == bot_id):
        return {"status": "ignored", "reason": "bot or subtype"}

    if event_type not in ("app_mention", "message"):
        logger.info("Slack webhook ignored: event_type=%r", event_type)
        return {"status": "ignored", "type": event_type}

    # Determine if the bot was directly addressed or is passively monitoring
    text_value = event.get("text", "")
    thread = event.get("thread_ts")
    if event_type == "app_mention" or (bot_id and f"<@{bot_id}>" in text_value):
        is_direct = True
    elif thread and bot_id and bot_participated_in_thread(channel, thread, bot_id):
        is_direct = True
    else:
        is_direct = False  # monitoring mode — agent decides whether to speak up

    event_id = payload.get("event_id")
    if event_id:
        if event_id in _SEEN_SLACK_EVENT_IDS:
            logger.info("Slack duplicate event_id=%s, ignoring", event_id)
            return {"status": "ignored", "reason": "duplicate"}
        _SEEN_SLACK_EVENT_IDS[event_id] = True
        if len(_SEEN_SLACK_EVENT_IDS) > _MAX_SEEN_SLACK_EVENTS:
            _SEEN_SLACK_EVENT_IDS.popitem(last=False)
    user_slack_id = event.get("user", "")
    text = re.sub(r"<@[A-Z0-9]+>\s*", "", event.get("text", "")).strip()
    raw_thread_ts = event.get("thread_ts")           # None if top-level mention
    thread_ts = raw_thread_ts or event.get("ts", "") # always set; used for reply threading

    if not channel or not text:
        return {"status": "ignored", "reason": "missing channel or text"}

    logger.info("Slack message: direct=%s user=%r channel=%r text=%r", is_direct, user_slack_id, channel, text[:200])

    user = load_user_context("slack", user_slack_id)

    def _run_slack():
        from skills.slack import _fetch_channel_context, client as slack_client, send_slack_message

        hist = memory.load(user)
        context = _fetch_channel_context(channel, thread_ts=raw_thread_ts)
        trello_ctx = _trello_context()

        # Run agent with channel context prepended, but save only the clean exchange to memory
        if is_direct:
            preamble = (
                f"[You are in a Slack conversation. Channel: {channel}. "
                f"Your text response will be posted as a thread reply. "
                f"If the user asks you to post something to the main channel (not the thread), "
                f"call send_slack_message(\"{channel}\", text) instead of replying inline. "
                f"Use judgment: conversational replies go in the thread; "
                f"content the user wants visible in the channel goes via send_slack_message.]"
            )
        else:
            preamble = (
                f"[You are silently monitoring Slack channel {channel}. "
                f"Read the conversation and decide if the group has reached a clear consensus or made a decision. "
                f"ONLY reply if you are confident a decision has been reached — "
                f"reply in the thread of that message asking: \"Should I log this decision?\" "
                f"followed by a brief summary of what was decided. "
                f"For general discussion, questions, or anything inconclusive: return EMPTY text. "
                f"Do not acknowledge you are watching unless you have something to log.]"
            )
        body = f"{context}\n\n---\n\n{text}" if context else text
        if trello_ctx:
            body = f"{trello_ctx}\n\n---\n\n{body}"
        enriched = f"{preamble}\n\n{body}"
        agent_hist = list(hist)
        agent_hist.append({"role": "user", "content": enriched})

        try:
            response_text, skill_name, actions_taken = agent.run(agent_hist, user=user, mode="chat")
        except Exception:
            logger.exception("Agent loop error for Slack user %s", user.user_id)
            send_slack_message(channel, "Sorry, something went wrong.")
            return

        hist.append({"role": "user", "content": text})
        hist.append({"role": "assistant", "content": response_text})
        memory.save(hist, user)

        if response_text:
            try:
                slack_client.chat_postMessage(
                    channel=channel,
                    text=response_text,
                    thread_ts=thread_ts,
                )
                logger.info("Slack reply sent: skill=%s actions=%s", skill_name, actions_taken)
            except Exception:
                logger.exception("Failed to send Slack reply to channel=%r", channel)

    background_tasks.add_task(_run_slack)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5055))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
