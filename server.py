import base64
import collections
import hashlib
import hmac
import logging
import os
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
from user import load_user, load_user_by_telegram_chat_id

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
    yield


app = FastAPI(title="Personal Assistant", lifespan=lifespan)

# Dedup Telegram updates by update_id — keeps last 1000 to bound memory
_SEEN_UPDATE_IDS: collections.OrderedDict = collections.OrderedDict()
_MAX_SEEN_UPDATES = 1000

_CAPTURE_API_KEY = os.environ.get("CAPTURE_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key")


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


def _capture_context() -> str:
    """Return a pre-fetched Trello overview and Obsidian file list for the capture prompt."""
    lines = []

    try:
        cache = _get_cache()
        lines.append("## Trello Boards & Lists\n")
        lines.append(_compact_overview(cache))
    except Exception as e:
        lines.append(f"## Trello Boards & Lists\n(unavailable: {e})")

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
        user = load_user(username)
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
            if response_text and user.telegram_chat_id:
                ok = telegram_send(user.telegram_chat_id, response_text)
                logger.info("Capture telegram send to %s: %s", user.telegram_chat_id, "ok" if ok else "failed")
            else:
                logger.warning("Capture: no telegram_chat_id for user %s or empty response", username)
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

    user = load_user_by_telegram_chat_id(chat_id)
    if user is None:
        logger.warning("Unknown Telegram chat_id: %r", chat_id)
        return {"status": "ignored", "reason": "unknown chat_id"}

    hist = memory.load(user)
    hist.append({"role": "user", "content": text})

    try:
        response_text, skill_name, actions_taken = agent.run(hist, user=user, mode="command")
    except Exception as e:
        logger.exception("Agent loop error for Telegram user %s", user.username)
        telegram_send(chat_id, "Sorry, something went wrong.")
        return {"status": "error", "detail": str(e)}

    memory.save(hist, user)

    if response_text:
        telegram_send(chat_id, response_text)

    logger.info("Telegram reply sent: skill=%s actions=%s", skill_name, actions_taken)
    return {"status": "ok", "skill": skill_name, "actions_taken": actions_taken}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5055))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
