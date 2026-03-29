---
description: Manage calendar events, reminders, and scheduling.
---

# Calendar

## When to use
Requests to create, read, update, or delete calendar events; reminders; scheduling questions;
"what's on my calendar", "remind me", "add an event", "free time this week".

## Guidelines
- Default time range for queries: next 7 days
- Default reminder time if not specified: use user's preferred default_reminder_time (fallback: 09:00)
- Always confirm the timezone used when creating events
- Avoid double-booking — check existing events before creating new ones
- All-day events should be created as all-day, not as 00:00–23:59

## Tools
Provided by the Google Calendar MCP connector (gcal.mcp.claude.com).
Use the MCP tools directly — do not call local stub functions.

## Output format
List events in chronological order. Include date, time, title, and location if set.
Use ISO 8601 for internal operations; display in human-readable local format.
