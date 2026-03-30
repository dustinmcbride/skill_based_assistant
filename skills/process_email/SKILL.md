---
description: process incoming emails using AgentMail.
---

# Email

## When to use
When an incoming email needs to be parsed, triaged, or acted on — e.g. extracting
trip details, summarizing a message, or responding to an email that has been received.
Not for on-demand inbox checking.

## Guidelines
- Use `get_email_thread` to read the full content of a specific thread
- Use `list_email_threads` only when you need context around a specific incoming message
- Requires `AGENTMAIL_INBOX_ID` and `AGENTMAIL_API_KEY` environment variables
- Never send or delete email unless explicitly asked

## Trip detection
When an email contains travel information — flights, hotels, car rentals, itineraries —
invoke the trips skill to extract and file it.

## Output format
List threads with: date, sender, subject, and a one-line preview.
For full thread reads, show each message with sender, date, and body.
