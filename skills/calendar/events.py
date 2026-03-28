"""
Calendar skill — stub implementation backed by a local JSON file.
In production, replace dispatch logic with a real calendar API (Google Calendar via MCP, etc.).
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from config import ASSISTANT_DIR
from skills import register

_CALENDAR_FILE = ASSISTANT_DIR / "calendar.json"


def _load() -> list[dict]:
    if not _CALENDAR_FILE.exists():
        return []
    try:
        return json.loads(_CALENDAR_FILE.read_text())
    except Exception:
        return []


def _save(events: list[dict]) -> None:
    _CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CALENDAR_FILE.write_text(json.dumps(events, indent=2))


@register
def create_event(title: str, start: str, end: str, description: str = "", location: str = "") -> str:
    """
    Create a calendar event.

    Args:
        title: Event title
        start: Start datetime in ISO 8601 format (e.g. 2024-03-15T09:00:00)
        end: End datetime in ISO 8601 format
        description: Optional event description
        location: Optional location
    """
    try:
        events = _load()
        event = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "start": start,
            "end": end,
            "description": description,
            "location": location,
            "created_at": datetime.utcnow().isoformat(),
        }
        events.append(event)
        _save(events)
        return f"Created event '{title}' from {start} to {end} (id: {event['id']})"
    except Exception as e:
        return f"Error creating event: {e}"


@register
def list_events(start_date: str = "", end_date: str = "") -> str:
    """
    List calendar events. Optionally filter by date range (ISO 8601 dates).

    Args:
        start_date: Start of range (YYYY-MM-DD), defaults to today
        end_date: End of range (YYYY-MM-DD), defaults to 7 days from start
    """
    try:
        from datetime import timedelta

        events = _load()
        if not events:
            return "No events found."

        today = datetime.utcnow().date()
        start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else start + timedelta(days=7)

        filtered = []
        for e in events:
            try:
                event_date = datetime.fromisoformat(e["start"]).date()
                if start <= event_date <= end:
                    filtered.append(e)
            except Exception:
                pass

        if not filtered:
            return f"No events between {start} and {end}."

        filtered.sort(key=lambda e: e["start"])
        lines = []
        for e in filtered:
            loc = f" @ {e['location']}" if e.get("location") else ""
            lines.append(f"[{e['id']}] {e['start']} – {e['end']}: {e['title']}{loc}")
            if e.get("description"):
                lines.append(f"     {e['description']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing events: {e}"


@register
def delete_event(event_id: str) -> str:
    """Delete a calendar event by its ID."""
    try:
        events = _load()
        original_count = len(events)
        events = [e for e in events if e.get("id") != event_id]
        if len(events) == original_count:
            return f"No event found with id '{event_id}'."
        _save(events)
        return f"Deleted event {event_id}."
    except Exception as e:
        return f"Error deleting event: {e}"
