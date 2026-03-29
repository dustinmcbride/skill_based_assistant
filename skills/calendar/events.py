"""
Calendar skill — backed by Google Calendar API using OAuth2 refresh token.

Required env vars:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    GOOGLE_REFRESH_TOKEN
"""

import os
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from skills import register

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds)


@register
def list_events(start_date: str = "", end_date: str = "") -> str:
    """
    List Google Calendar events. Optionally filter by date range (YYYY-MM-DD).

    Args:
        start_date: Start of range (YYYY-MM-DD), defaults to today
        end_date: End of range (YYYY-MM-DD), defaults to 7 days from start
    """
    try:
        today = datetime.now(timezone.utc).date()
        start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else start + timedelta(days=7)

        time_min = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()
        time_max = datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc).isoformat()

        service = _get_service()
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"No events between {start} and {end}."

        lines = []
        for e in events:
            start_val = e["start"].get("dateTime", e["start"].get("date", ""))
            end_val = e["end"].get("dateTime", e["end"].get("date", ""))
            location = f" @ {e['location']}" if e.get("location") else ""
            lines.append(f"[{e['id'][:8]}] {start_val} – {end_val}: {e.get('summary', '(no title)')}{location}")
            if e.get("description"):
                lines.append(f"     {e['description'][:120]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing events: {e}"


@register
def create_event(title: str, start: str, end: str, description: str = "", location: str = "") -> str:
    """
    Create a Google Calendar event.

    Args:
        title: Event title
        start: Start datetime in ISO 8601 format (e.g. 2024-03-15T09:00:00)
        end: End datetime in ISO 8601 format
        description: Optional event description
        location: Optional location
    """
    try:
        service = _get_service()
        body = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        event = service.events().insert(calendarId="primary", body=body).execute()
        return f"Created event '{title}' from {start} to {end} (id: {event['id'][:8]})"
    except Exception as e:
        return f"Error creating event: {e}"


@register
def delete_event(event_id: str) -> str:
    """Delete a Google Calendar event by its ID."""
    try:
        service = _get_service()
        # Support short IDs by searching first
        if len(event_id) <= 8:
            result = service.events().list(
                calendarId="primary",
                timeMin=datetime.now(timezone.utc).isoformat(),
                maxResults=100,
                singleEvents=True,
            ).execute()
            matches = [e for e in result.get("items", []) if e["id"].startswith(event_id)]
            if not matches:
                return f"No event found with id starting with '{event_id}'."
            if len(matches) > 1:
                return f"Multiple events match '{event_id}'. Please use a more specific id."
            event_id = matches[0]["id"]

        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return f"Deleted event {event_id[:8]}."
    except Exception as e:
        return f"Error deleting event: {e}"
