import json
import os

import httpx

from skills import register

_BASE_URL = "https://api.agentmail.to/v0"


def _headers() -> dict:
    api_key = os.environ.get("AGENTMAIL_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _inbox_id() -> str:
    return os.environ.get("AGENTMAIL_INBOX_ID", "")


@register
def lookup_email_recipient(name: str) -> str:
    """Look up a known user by name or user ID to get their email address and persona.
    Returns a JSON object with 'email', 'name', and 'persona' for drafting a tailored email.
    If not found, returns an error — ask the sender for the address instead.
    """
    from config import _CONFIG, USER_PERSONAS

    name_lower = name.strip().lower()
    for entry in _CONFIG.get("users", []):
        user_id = entry.get("id", "")
        display_name = entry.get("name", "")
        if name_lower == user_id.lower() or name_lower == display_name.lower():
            email = entry.get("email")
            if not email:
                return json.dumps({"error": f"User '{display_name}' has no email address configured."})
            persona = USER_PERSONAS.get(user_id, "")
            return json.dumps({
                "email": email,
                "user_id": user_id,
                "name": display_name,
                "persona": persona or "No persona configured for this user.",
            })

    known = [e.get("name") or e.get("id") for e in _CONFIG.get("users", []) if e.get("id")]
    return json.dumps({"error": f"No user found matching '{name}'. Known users: {known}"})


@register
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via AgentMail. Only call this after the user has confirmed the draft.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body
    """
    inbox_id = _inbox_id()
    if not inbox_id:
        return "Error: AGENTMAIL_INBOX_ID environment variable not set."

    try:
        resp = httpx.post(
            f"{_BASE_URL}/inboxes/{inbox_id}/messages",
            headers=_headers(),
            json={"to": [to], "subject": subject, "text": body},
            timeout=15,
        )
        resp.raise_for_status()
        return f"Email sent to {to}."
    except httpx.HTTPStatusError as e:
        return f"API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error sending email: {e}"
