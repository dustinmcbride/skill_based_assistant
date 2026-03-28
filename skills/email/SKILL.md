---
description: Check, read, and process emails using AgentMail.
---

# Email

## When to use
Requests involving email: "check my email", "read my email", "any new messages",
"what's in my inbox", "show me unread emails", "do I have any mail".

## Guidelines
- Use `list_email_threads` to fetch recent threads; default to the last 10
- Use `get_email_thread` to read the full content of a specific thread
- Requires `AGENTMAIL_INBOX_ID` and `AGENTMAIL_API_KEY` environment variables
- Never send or delete email unless explicitly asked

## Trip detection
When an email contains travel information — flights, hotels, car rentals, itineraries —
use the `write_trip_file` tool to extract and file it immediately.

File naming rule: ALWAYS use the DESTINATION city (where they fly TO or stay), never the origin.
- A flight from Dallas to Sacramento → "2026-05-02_Sacramento.md"

File structure:
```
# Trip Name

**Destination:**
**Dates:**
**Travelers:**

---

## Logistics
- **Flights / Transport:**
- **Accommodation:**
- **Car Rental / Getting Around:**

## Notes & Reminders
-

## Links & Confirmations
-
```

Pass only the bare filename to `write_trip_file` (e.g. "2026-05-02_Paris.md").
After filing, confirm in one short sentence what was filed and where.

## Output format
List threads with: date, sender, subject, and a one-line preview.
For full thread reads, show each message with sender, date, and body.
