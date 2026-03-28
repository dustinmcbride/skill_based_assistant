import base64
import hashlib
import hmac
import logging
import os
import sys
import time
from pathlib import Path

# Ensure assistant/ is on sys.path when running via uvicorn from project root
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

import agent
import memory
from skills.email.agentmail import get_email_thread
from user import load_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Assistant")

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


class CommandRequest(BaseModel):
    message: str


class CommandResponse(BaseModel):
    response: str
    skill: str | None = None
    actions_taken: list[str] = []


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/command/{username}", response_model=CommandResponse)
async def command(username: str, body: CommandRequest):
    try:
        user = load_user(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    hist = memory.load(user)
    hist.append({"role": "user", "content": body.message})

    try:
        response_text, skill_name, actions_taken = agent.run(
            hist, user=user, mode="command"
        )
    except Exception as e:
        logger.exception("Agent loop error for user %s", username)
        raise HTTPException(status_code=500, detail=str(e))

    memory.save(hist, user)
    return CommandResponse(
        response=response_text,
        skill=skill_name,
        actions_taken=actions_taken,
    )


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
        raise HTTPException(status_code=500, detail=str(e))
    logger.info("Webhook processed: skill=%s actions=%s", skill_name, actions_taken)
    return {"status": "ok", "skill": skill_name, "actions_taken": actions_taken}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5055))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
