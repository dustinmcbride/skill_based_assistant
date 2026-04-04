---
description: Send messages to Slack channels.
---

# Slack Skill

This skill provides a function to send messages to Slack channels using the Slack Bot token.

## When to use
- "Send a message to #channel"
- "Post in Slack..."
- "Notify the [channel] channel"
- "DM [person] on Slack"
- "Message [person] directly"
- "Who's in the Slack workspace?"

## Workflow

### Sending to a channel
Call `send_slack_message` with the channel name (e.g. `#general`) and the message text.

### Sending a DM
1. If you don't already have the user's Slack ID, call `list_slack_users` to find them by name.
2. Call `send_slack_dm` with their user ID and the message text.

## Requirements
- `SLACK_BOT_TOKEN` must be set in `.env`.
