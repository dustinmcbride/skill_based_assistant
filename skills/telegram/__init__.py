import json
import logging
import os

import httpx

from skills import register

logger = logging.getLogger(__name__)

_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def send_message(chat_id: str, text: str) -> bool:
    """Send a message to a Telegram chat. Returns True on success."""
    if not _BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set; cannot send message")
        return False
    url = _API_BASE.format(token=_BOT_TOKEN, method="sendMessage")
    resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    if not resp.is_success:
        logger.error("Telegram sendMessage failed: %s %s", resp.status_code, resp.text)
    return resp.is_success


@register
def lookup_telegram_recipient(name: str) -> str:
    """Look up a user by name or user ID to get their Telegram chat ID and persona.
    Returns a JSON object with 'chat_id' and 'persona' so you can draft a message
    tailored to the recipient before sending. Call this before send_telegram_message
    whenever messaging another user.
    """
    # Import here to avoid circular dependency at module load time
    from config import _CONFIG, USER_PERSONAS

    name_lower = name.strip().lower()
    for entry in _CONFIG.get("users", []):
        user_id = entry.get("id", "")
        display_name = entry.get("name", "")
        # Match on user ID or display name (case-insensitive)
        if name_lower == user_id.lower() or name_lower == display_name.lower():
            chat_id = entry.get("telegram_chat_id")
            if not chat_id:
                return json.dumps({"error": f"User '{display_name}' has no Telegram chat ID configured."})
            persona = USER_PERSONAS.get(user_id, "")
            return json.dumps({
                "chat_id": chat_id,
                "user_id": user_id,
                "name": display_name,
                "persona": persona or "No persona configured for this user.",
            })

    # Build a list of known names for the error message
    known = [e.get("name") or e.get("id") for e in _CONFIG.get("users", []) if e.get("id")]
    return json.dumps({"error": f"No user found matching '{name}'. Known users: {known}"})


@register
def send_telegram_message(chat_id: str, text: str) -> str:
    """Send a Telegram message to a specific chat ID. Use this to notify or message a user via Telegram."""
    ok = send_message(chat_id, text)
    return "Message sent." if ok else "Failed to send message (check TELEGRAM_BOT_TOKEN)."
