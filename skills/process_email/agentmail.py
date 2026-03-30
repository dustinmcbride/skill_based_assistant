import os
from typing import Optional

import httpx

from skills import register

_BASE_URL = "https://api.agentmail.to/v0"


def _headers() -> dict:
    api_key = os.environ.get("AGENTMAIL_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _inbox_id() -> str:
    return os.environ.get("AGENTMAIL_INBOX_ID", "")


@register
def list_email_threads(limit: int = 10, label: Optional[str] = None) -> str:
    """
    List recent email threads from the inbox.

    Args:
        limit: Number of threads to return (default 10, max 50)
        label: Optional label filter (e.g. "UNREAD", "INBOX")
    """
    inbox_id = _inbox_id()
    if not inbox_id:
        return "Error: AGENTMAIL_INBOX_ID environment variable not set."

    params: dict = {"limit": min(limit, 50)}
    if label:
        params["labels"] = label

    try:
        resp = httpx.get(
            f"{_BASE_URL}/inboxes/{inbox_id}/threads",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return f"API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error fetching threads: {e}"

    threads = data.get("threads", data) if isinstance(data, dict) else data
    if not threads:
        return "No threads found."

    lines = []
    for t in threads:
        date = t.get("received_timestamp") or t.get("timestamp") or ""
        senders = ", ".join(t.get("senders", [])) or "unknown"
        subject = t.get("subject", "(no subject)")
        preview = t.get("preview", "")
        thread_id = t.get("thread_id", "")
        lines.append(f"[{date}] {senders} — {subject}\n  ID: {thread_id}\n  {preview}")

    return "\n\n".join(lines)


@register
def get_email_thread(thread_id: str) -> str:
    """
    Get the full content of an email thread by ID.

    Args:
        thread_id: The thread ID to retrieve
    """
    inbox_id = _inbox_id()
    if not inbox_id:
        return "Error: AGENTMAIL_INBOX_ID environment variable not set."

    try:
        resp = httpx.get(
            f"{_BASE_URL}/inboxes/{inbox_id}/threads/{thread_id}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return f"API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error fetching thread: {e}"

    subject = data.get("subject", "(no subject)")
    messages = data.get("messages", [])
    if not messages:
        return f"Thread '{subject}' has no messages."

    lines = [f"# {subject}\n"]
    for msg in messages:
        sender = msg.get("from", "unknown")
        date = msg.get("timestamp", "")

        # Try inline body first, then fetch from body_url if empty
        body = msg.get("body", {})
        text = (
            msg.get("extracted_text")
            or msg.get("text")
            or (body.get("text") if isinstance(body, dict) else None)
            or (body.get("html") if isinstance(body, dict) else None)
        )
        if not text:
            body_url = msg.get("body_url", "")
            if body_url:
                try:
                    body_resp = httpx.get(body_url, timeout=15)
                    body_resp.raise_for_status()
                    body_data = body_resp.json()
                    text = (
                        body_data.get("extracted_text")
                        or body_data.get("text")
                        or body_data.get("html")
                        or ""
                    )
                except Exception:
                    pass
        if not text:
            text = msg.get("preview", "")

        lines.append(f"**From:** {sender}  \n**Date:** {date}\n\n{text}")

    return "\n\n---\n\n".join(lines)
