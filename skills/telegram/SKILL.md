---
description: Send Telegram messages to other users, tailored to the recipient's persona.
---

# Telegram messaging skill

Use this skill when the user wants to send a message to another person via Telegram,
forward information to someone, or notify another user.

## When to use
- "Send [person] a message about..."
- "Tell [person] that..."
- "Let [person] know..."
- "Message [person]..."
- "Forward this to [person]"

## Workflow

1. **Look up the recipient** — call `lookup_telegram_recipient` with the recipient's name or user ID. This returns their `chat_id` and persona description.
2. **Draft the message using their persona** — read the persona carefully. Tailor the tone, vocabulary, level of detail, and framing to suit *how this person communicates and what they care about*. The message should feel like it was written for them specifically, not a generic relay.
3. **Send** — call `send_telegram_message` with the `chat_id` from step 1 and the persona-tailored text.

## Persona-aware drafting

The persona tells you how to speak to this person. For example:
- A recipient described as casual and emoji-friendly → use informal language and emoji
- A recipient described as concise and task-oriented → be brief and direct
- A recipient described as warm and conversational → be friendly, add context

Do not just forward the sender's words verbatim. Reframe the content so it lands well for the recipient.

## Confirming to the sender

After sending, confirm briefly to the sender what was sent and to whom.
