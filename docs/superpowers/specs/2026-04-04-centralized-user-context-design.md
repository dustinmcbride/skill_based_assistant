# Centralized User Context Design

**Date:** 2026-04-04
**Status:** Approved

## Problem

User identity and context are currently fragmented across channels. Telegram and Slack histories are stored in separate silos with no cross-channel awareness. Persona injection only works when a user is pre-configured. There is no central place for outbound messages, so cross-user messaging bypasses persona adaptation and history logging.

## Goals

1. All agents always know what persona to use when addressing a user
2. Cross-channel activity is summarized and available in every session
3. Anonymous users (no config entry) are supported with a generic default persona
4. All outbound messages flow through a single dispatch function that applies the recipient's persona and logs to their history

## Approach: `UserContext` Object (Approach B)

A single `UserContext` object is assembled once per request and passed through the entire system — agent, memory, and dispatch all speak the same language.

---

## 1. UserContext

**New file:** `user_context.py` (replaces `user.py`)

```python
@dataclass
class UserContext:
    user_id: str          # "dustin" or "anon-slack-U09XYZ"
    display_name: str     # "Tim Fish" or "Unknown User"
    persona: str          # Loaded persona markdown or DEFAULT_PERSONA
    active_channel: str   # "telegram" | "slack" | "cli" | "email"
    channels: dict        # {"telegram": "6211085845", "slack": "U09JULETA74"}
    history_path: Path    # memory/users/<user_id>/<channel>/history.json
    cross_channel_summary: str  # Injected into system prompt; "" if none
    is_anonymous: bool    # True if no config entry matched
```

**Identity resolution — two entry points:**

`load_user_context(channel: str, channel_id: str) -> UserContext` — used by webhook handlers (Telegram, Slack):
1. Scan config users for one whose `channels[channel] == channel_id`
2. If found → build `UserContext` with their persona (loaded from `persona_url`) and full channel map
3. If not found → build anonymous `UserContext` with:
   - `user_id = "anon-{channel}-{channel_id}"`
   - `display_name = "Unknown User"`
   - `persona = DEFAULT_PERSONA` (generic, friendly, professional)
   - `is_anonymous = True`

`load_user_context_by_id(user_id: str, channel: str = "cli") -> UserContext` — used by `run.py` (CLI), where the user is specified by username rather than a channel ID. Raises if the user is not found (CLI sessions always have a known user).

**`preferred_channel` for cross-user messaging:** When the agent needs to send a message to a user and no active channel is implied, use the first available channel in `channels` (order: telegram → slack → email).

---

## 2. Config Schema

The flat `telegram_chat_id`, `slack_user_id`, and `email` fields on user entries are replaced by a single `channels` dict:

```json
{
  "id": "dustin",
  "name": "Tim Fish",
  "persona_url": "file:///path/to/persona.md",
  "channels": {
    "telegram": "6211085845",
    "slack": "U09JULETA74",
    "email": "dustin@example.com"
  },
  "skills": {}
}
```

---

## 3. Memory Layout

All history is stored under a unified per-user, per-channel structure. No migration of existing history is needed — start fresh.

```
memory/
└── users/
    ├── dustin/
    │   ├── telegram/history.json
    │   ├── slack/history.json
    │   └── cli/history.json
    └── anon-slack-U09XYZ/
        └── slack/history.json
```

`memory.load(ctx)` and `memory.save(history, ctx)` use `ctx.history_path` — no other signature changes needed.

---

## 4. Cross-Channel Summary

Built once at request time and stored on `ctx.cross_channel_summary`. Injected into the system prompt under a `## Recent activity across channels` section. Omitted entirely if the user has only used one channel.

**Lookback rules (hardcoded):**
- Last 5 messages per channel
- Within the last 30 days
- Both limits apply; whichever is more restrictive wins

**Generation:** A single Opus call with the raw messages from other channels produces a plain-text summary capped at ~100 words.

**Example system prompt injection:**
```
## Recent activity across channels
- Slack (2 days ago): Asked about the NYC trip and requested a calendar block for Friday.
- Email (yesterday): Received and filed a Delta itinerary.
```

---

## 5. Central Message Dispatch (`messaging.py`)

**New file:** `messaging.py`

```python
def send_message(recipient: UserContext, draft: str) -> str:
    ...
```

**Steps:**
1. **Persona adaptation** — make an Opus call with `recipient.persona` as the system prompt to adapt the tone/style of `draft`. `send_message` is only called for agent-initiated outbound messages (cross-user forwards, notifications); inline replies within a session go through the normal agent return path where the persona is already in the system prompt.
2. **Channel routing** — route to the appropriate transport based on `recipient.active_channel` (or preferred channel order `telegram → slack → email` if no active session): `send_telegram_message`, `send_slack_dm`, etc.
3. **History logging** — append the sent message to `recipient.history_path` so future sessions with that user include it.

Existing transport functions (`send_telegram_message`, `send_slack_dm`) remain unchanged as the underlying transport layer.

---

## 6. Files Changed

| File | Change |
|------|--------|
| `user_context.py` | New — replaces `user.py` |
| `messaging.py` | New — central dispatch |
| `memory.py` | Updated path structure; add `build_cross_channel_summary()` |
| `agent.py` | Accept `UserContext`; inject `cross_channel_summary` into system prompt |
| `server.py` | Webhook handlers call `load_user_context(channel, id)` |
| `config.py` | Remove `USER_PERSONAS` dict; persona loading moves to `user_context.py` |
| `run.py` | Use `UserContext` for CLI sessions |
| `config.json` | Update user entries to `channels` dict schema |
| `user.py` | Deleted — replaced by `user_context.py` |

---

## Out of Scope

- Message queue or persistent audit log of outbound messages
- User profile creation via conversation (anonymous users stay anonymous)
- Configurable lookback window (hardcoded)
