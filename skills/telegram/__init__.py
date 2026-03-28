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
def send_telegram_message(chat_id: str, text: str) -> str:
    """Send a Telegram message to a specific chat ID. Use this to notify or message a user via Telegram."""
    ok = send_message(chat_id, text)
    return "Message sent." if ok else "Failed to send message (check TELEGRAM_BOT_TOKEN)."
