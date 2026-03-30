---
description: Compose and send an email 
---

# Send Email

## When to use
- "Email [person] about..."
- "Send [person] a message"
- "Write an email to..."
- "Let [person] know via email..."

## Workflow

### 1. Resolve the recipient

**Known user** (name matches someone in the system):
- Call `lookup_email_recipient` with their name
- Use the returned `email`, `name`, and `persona`

**External or unknown recipient** (email address provided directly):
- Use the address as given — no lookup needed
- Write in a neutral, professional tone

### 2. Draft the email — persona-aware

When a persona is available, read it carefully and tailor:
- **Tone** — casual vs. formal, warm vs. direct
- **Length** — brief or detailed based on their preferences
- **Framing** — what they care about, how they like information presented

Do not copy the sender's words verbatim. Rewrite the content so it lands well for this recipient.

### 3. Show the draft before sending — always

Present the full draft in this format, then ask *"Send this?"*:

```
**To:** recipient@example.com
**Subject:** Subject line here

Body of the email here.
```

Wait for explicit confirmation before calling `send_email`. Do not send automatically.

### 4. Send and confirm

Call `send_email` only after the user confirms. Then reply with one short sentence:
- "Sent to Savanna at savanna@example.com — subject: Dinner plans."
