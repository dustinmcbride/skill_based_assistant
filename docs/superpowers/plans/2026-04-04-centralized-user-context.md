# Centralized User Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragmented `User` + `USER_PERSONAS` system with a single `UserContext` object that carries identity, persona, channel map, history path, and cross-channel activity summary — passed through every layer of the system.

**Architecture:** A new `user_context.py` replaces `user.py`. Two lookup functions — one for webhook channels (anonymous-safe), one for CLI (username-based) — assemble a `UserContext` once per request. A new `messaging.py` is the single dispatch point for all agent-initiated outbound messages; it adapts tone using the recipient's persona, routes to the right channel, and logs to the recipient's history. Memory paths move from `memory/users/<id>/history.json` to `memory/users/<id>/<channel>/history.json`.

**Tech Stack:** Python 3.11+, Anthropic Python SDK (`anthropic`), FastAPI, slack-sdk, httpx. Tests use pytest + monkeypatch.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `user_context.py` | Create | `UserContext` dataclass, identity resolution, persona loading, cross-channel summary |
| `messaging.py` | Create | Central outbound message dispatch |
| `memory.py` | Modify | Fix `user.username` → `user.user_id` in log; `load`/`save` work unchanged (both use `history_path`) |
| `agent.py` | Modify | Accept `UserContext`, inject `cross_channel_summary` into system prompt, remove `USER_PERSONAS` |
| `server.py` | Modify | Use `load_user_context` / `load_user_context_by_id`; anonymous Telegram users now get a context |
| `run.py` | Modify | Use `load_user_context_by_id` |
| `config.py` | Modify | Remove `_load_personas()` and `USER_PERSONAS` export |
| `config.json` | Modify | Migrate flat channel fields to `channels` dict |
| `skills/telegram/__init__.py` | Modify | Update `lookup_telegram_recipient` to use `channels` dict and `_load_persona` |
| `tests/test_user_context.py` | Create | Tests for `UserContext`, identity resolution, history isolation |
| `tests/test_messaging.py` | Create | Tests for `send_message` dispatch |
| `tests/test_users.py` | Delete | Replaced by `test_user_context.py` |
| `tests/test_command_mode.py` | Modify | Update fixture to use `UserContext` instead of `User` |
| `user.py` | Delete | Replaced by `user_context.py` |

---

## Task 1: Update `config.json` to channels schema

**Files:**
- Modify: `config.json`

- [ ] **Step 1: Replace flat channel fields with `channels` dict**

Replace the contents of `config.json` with:

```json
{
  "soul_base_url": "file:///Users/dustinmcbride/git/self-hosted/assistant/office_of_tim_fish/soul.md",
  "additional_skill_context_url": "file:///Users/dustinmcbride/git/self-hosted/assistant/office_of_tim_fish/additional_skill_context.md",
  "external_skill_dirs": [
    "file:///Users/dustinmcbride/git/self-hosted/assistant/skills/sauna/"
  ],
  "users": [
    {
      "id": "dustin",
      "name": "Tim Fish",
      "persona_url": "file:///Users/dustinmcbride/git/self-hosted/assistant/office_of_tim_fish/personas/dustin.md",
      "channels": {
        "telegram": "6211085845",
        "slack": "U09JULETA74",
        "email": "dustin@example.com"
      },
      "skills": {
        "sauna": {
          "login": "dustinbm@gmail.com",
          "password": "cidhog-cutto9-mujMiv"
        }
      }
    },
    {
      "id": "savanna",
      "name": "Savanna",
      "persona_url": "file:///Users/dustinmcbride/git/self-hosted/assistant/office_of_tim_fish/personas/savanna.md",
      "channels": {
        "telegram": "-5241403184",
        "slack": "U09JN8JGW1Z",
        "email": "savanna@example.com"
      }
    }
  ]
}
```

- [ ] **Step 2: Commit**

```bash
git add config.json
git commit -m "feat: migrate config.json to channels dict schema"
```

---

## Task 2: Write failing tests for `user_context.py`

**Files:**
- Create: `tests/test_user_context.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_user_context.py`:

```python
"""Tests for UserContext identity resolution and history isolation."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_username_re_valid():
    from user_context import USERNAME_RE
    for name in ["tim", "tina", "user-123", "a", "abc-def-ghi"]:
        assert USERNAME_RE.match(name), f"{name!r} should be valid"


def test_username_re_invalid():
    from user_context import USERNAME_RE
    for name in ["../etc/passwd", "UPPER", "has space", "has/slash"]:
        assert not USERNAME_RE.match(name), f"{name!r} should be invalid"


def test_load_user_context_by_id_raises_for_unknown(monkeypatch):
    monkeypatch.setattr("user_context._KNOWN_USERS", {})
    from user_context import load_user_context_by_id
    with pytest.raises(ValueError, match="Unknown user"):
        load_user_context_by_id("nobody")


def test_load_user_context_by_id_known_user(tmp_path, monkeypatch):
    monkeypatch.setattr("user_context.ASSISTANT_DIR", tmp_path)
    monkeypatch.setattr("user_context._KNOWN_USERS", {
        "alice": {
            "id": "alice",
            "name": "Alice Smith",
            "channels": {"telegram": "12345", "slack": "U111"},
            "persona_url": None,
        }
    })
    monkeypatch.setattr("user_context.build_cross_channel_summary", lambda ctx: "")

    from user_context import load_user_context_by_id
    ctx = load_user_context_by_id("alice", channel="cli")

    assert ctx.user_id == "alice"
    assert ctx.display_name == "Alice Smith"
    assert ctx.active_channel == "cli"
    assert ctx.channels == {"telegram": "12345", "slack": "U111"}
    assert ctx.history_path == tmp_path / "users" / "alice" / "cli" / "history.json"
    assert ctx.is_anonymous is False


def test_load_user_context_anonymous(tmp_path, monkeypatch):
    monkeypatch.setattr("user_context._CONFIG", {"users": []})
    monkeypatch.setattr("user_context.ASSISTANT_DIR", tmp_path)

    from user_context import load_user_context
    ctx = load_user_context("telegram", "99999")

    assert ctx.user_id == "anon-telegram-99999"
    assert ctx.is_anonymous is True
    assert ctx.active_channel == "telegram"
    assert ctx.history_path == tmp_path / "users" / "anon-telegram-99999" / "telegram" / "history.json"
    assert ctx.cross_channel_summary == ""


def test_load_user_context_finds_by_channel_id(tmp_path, monkeypatch):
    monkeypatch.setattr("user_context.ASSISTANT_DIR", tmp_path)
    monkeypatch.setattr("user_context._CONFIG", {
        "users": [
            {
                "id": "bob",
                "name": "Bob",
                "channels": {"telegram": "55555", "slack": "UBOB"},
                "persona_url": None,
            }
        ]
    })
    monkeypatch.setattr("user_context.build_cross_channel_summary", lambda ctx: "")

    from user_context import load_user_context
    ctx = load_user_context("telegram", "55555")

    assert ctx.user_id == "bob"
    assert ctx.is_anonymous is False
    assert ctx.channels == {"telegram": "55555", "slack": "UBOB"}


def test_history_path_per_channel(tmp_path, monkeypatch):
    """Same user on different channels gets different history paths."""
    monkeypatch.setattr("user_context.ASSISTANT_DIR", tmp_path)
    monkeypatch.setattr("user_context._KNOWN_USERS", {
        "alice": {
            "id": "alice",
            "name": "Alice",
            "channels": {"telegram": "1", "slack": "U1"},
            "persona_url": None,
        }
    })
    monkeypatch.setattr("user_context.build_cross_channel_summary", lambda ctx: "")

    from user_context import load_user_context_by_id
    telegram_ctx = load_user_context_by_id("alice", channel="telegram")
    slack_ctx = load_user_context_by_id("alice", channel="slack")

    assert telegram_ctx.history_path != slack_ctx.history_path
    assert "telegram" in str(telegram_ctx.history_path)
    assert "slack" in str(slack_ctx.history_path)


def test_history_isolation_with_user_context(tmp_path):
    """Two users have separate history files."""
    import memory
    from user_context import UserContext

    def make_ctx(user_id, channel="telegram"):
        return UserContext(
            user_id=user_id,
            display_name=user_id.capitalize(),
            persona="",
            active_channel=channel,
            channels={channel: "123"},
            history_path=tmp_path / "users" / user_id / channel / "history.json",
            cross_channel_summary="",
            is_anonymous=False,
        )

    alice = make_ctx("alice")
    bob = make_ctx("bob")

    memory.save([{"role": "user", "content": "hello from alice"}], alice)
    memory.save([{"role": "user", "content": "hello from bob"}], bob)

    assert memory.load(alice)[0]["content"] == "hello from alice"
    assert memory.load(bob)[0]["content"] == "hello from bob"


def test_anonymous_persona_is_default():
    from user_context import DEFAULT_PERSONA, load_user_context
    # monkeypatch not needed since no real config matches "unknown_channel"
    ctx = load_user_context("unknown_channel", "00000")
    assert ctx.persona == DEFAULT_PERSONA


def test_memory_trim():
    """Trim keeps last N complete user turns (unchanged from old test_users.py)."""
    import memory
    hist = []
    for i in range(50):
        hist.append({"role": "user", "content": f"msg {i}"})
        hist.append({"role": "assistant", "content": f"resp {i}"})
    trimmed = memory.trim(hist, max_turns=10)
    user_msgs = [m for m in trimmed if m["role"] == "user"]
    assert len(user_msgs) == 10
    assert trimmed[0]["role"] == "user"
```

- [ ] **Step 2: Run tests to verify they fail (module not found)**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_user_context.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'user_context'`

---

## Task 3: Create `user_context.py`

**Files:**
- Create: `user_context.py`

- [ ] **Step 1: Write `user_context.py`**

```python
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

from config import AGENT_MODEL, ASSISTANT_DIR, _CONFIG, _load_url

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_PERSONA = (
    "You are speaking with a user who has not set up a profile. "
    "Be friendly, professional, and helpful."
)

_KNOWN_USERS: dict[str, dict] = {
    entry["id"]: entry
    for entry in _CONFIG.get("users", [])
    if "id" in entry
}


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


def _load_persona(persona_url: str | None) -> str:
    """Load persona markdown from a URL. Returns DEFAULT_PERSONA on failure or missing URL."""
    if not persona_url:
        return DEFAULT_PERSONA
    try:
        return _load_url(persona_url)
    except Exception as e:
        logger.warning("Failed to load persona from %s: %s", persona_url, e)
        return DEFAULT_PERSONA


def build_cross_channel_summary(ctx: "UserContext") -> str:
    """
    Build a brief cross-channel activity summary for injection into the system prompt.

    Reads the last 5 user turns from each channel directory that is NOT the active
    channel. Returns "" if no other channel history exists or on any error.

    Note: history files do not store timestamps, so the 30-day lookback is
    approximated by the last 5 user turns only.
    """
    user_dir = ASSISTANT_DIR / "users" / ctx.user_id
    if not user_dir.exists():
        return ""

    channel_snippets: list[tuple[str, list[str]]] = []
    for channel_dir in sorted(user_dir.iterdir()):
        if not channel_dir.is_dir() or channel_dir.name == ctx.active_channel:
            continue
        history_file = channel_dir / "history.json"
        if not history_file.exists():
            continue
        try:
            history = json.loads(history_file.read_text())
        except Exception:
            continue

        # Last 5 user turns (excluding tool result turns)
        user_turns = [
            m for m in history
            if m.get("role") == "user"
            and not (
                isinstance(m.get("content"), list)
                and any(
                    b.get("type") == "tool_result"
                    for b in m["content"]
                    if isinstance(b, dict)
                )
            )
        ][-5:]

        texts: list[str] = []
        for turn in user_turns:
            content = turn["content"]
            if isinstance(content, str):
                texts.append(content[:200])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block["text"][:200])
                        break

        if texts:
            channel_snippets.append((channel_dir.name, texts))

    if not channel_snippets:
        return ""

    raw_lines: list[str] = []
    for channel_name, texts in channel_snippets:
        raw_lines.append(f"Channel: {channel_name}")
        for t in texts:
            raw_lines.append(f"  - {t}")

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=200,
            system=(
                "Summarize the following recent user activity across channels. "
                "Output bullet points in the format '- ChannelName: brief summary'. "
                "Cap at 100 words total. Be very concise."
            ),
            messages=[{"role": "user", "content": "\n".join(raw_lines)}],
        )
        return "## Recent activity across channels\n" + response.content[0].text
    except Exception as e:
        logger.warning("Failed to generate cross-channel summary: %s", e)
        return ""


def _build_context(entry: dict, channel: str) -> "UserContext":
    user_id = entry["id"]
    channels = entry.get("channels", {})
    persona = _load_persona(entry.get("persona_url"))
    history_path = ASSISTANT_DIR / "users" / user_id / channel / "history.json"
    ctx = UserContext(
        user_id=user_id,
        display_name=entry.get("name") or user_id.capitalize(),
        persona=persona,
        active_channel=channel,
        channels=channels,
        history_path=history_path,
        cross_channel_summary="",
        is_anonymous=False,
    )
    ctx.cross_channel_summary = build_cross_channel_summary(ctx)
    return ctx


def load_user_context(channel: str, channel_id: str) -> "UserContext":
    """
    Look up a user by channel + channel_id.
    Returns an anonymous UserContext if no matching user is found in config.
    Used by webhook handlers (Telegram, Slack).
    """
    for entry in _CONFIG.get("users", []):
        channels = entry.get("channels", {})
        if str(channels.get(channel, "")) == str(channel_id):
            return _build_context(entry, channel)

    # No match — anonymous user
    user_id = f"anon-{channel}-{channel_id}"
    return UserContext(
        user_id=user_id,
        display_name="Unknown User",
        persona=DEFAULT_PERSONA,
        active_channel=channel,
        channels={channel: channel_id},
        history_path=ASSISTANT_DIR / "users" / user_id / channel / "history.json",
        cross_channel_summary="",
        is_anonymous=True,
    )


def load_user_context_by_id(user_id: str, channel: str = "cli") -> "UserContext":
    """
    Look up a user by user_id and channel.
    Raises ValueError if the user is not in config.
    Used by run.py (CLI) where the username is always known.
    """
    if user_id not in _KNOWN_USERS:
        raise ValueError(
            f"Unknown user {user_id!r}. Known users: {list(_KNOWN_USERS)}"
        )
    return _build_context(_KNOWN_USERS[user_id], channel)
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_user_context.py -v
```

Expected: All tests pass. If `test_anonymous_persona_is_default` fails because the real config has a matching entry, check that `_CONFIG` is loaded from the real config.json (which has channels, not old flat fields after Task 1).

- [ ] **Step 3: Commit**

```bash
git add user_context.py tests/test_user_context.py
git commit -m "feat: add UserContext with identity resolution and cross-channel summary"
```

---

## Task 4: Update `config.py` — remove `USER_PERSONAS`

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Remove `_load_personas` and `USER_PERSONAS`**

Delete lines 81–92 (the `_load_personas` function) and line 160 (`USER_PERSONAS: dict[str, str] = _load_personas()`).

The file should go from:

```python
def _load_personas() -> dict[str, str]:
    personas: dict[str, str] = {}
    for user_entry in _CONFIG.get("users", []):
        user_id = user_entry.get("id")
        persona_url = user_entry.get("persona_url")
        if not user_id or not persona_url:
            continue
        try:
            personas[user_id] = _load_url(persona_url)
        except Exception as e:
            logger.warning("Failed to load persona for %s: %s", user_id, e)
    return personas
```

...to that block being deleted entirely. Also remove this line at the bottom:

```python
USER_PERSONAS: dict[str, str] = _load_personas()
```

The bottom of `config.py` should now be:

```python
SOUL_CONTENT: str = _load_soul()
ADDITIONAL_SKILL_CONTEXT: str = _load_additional_skill_context()
EXTERNAL_SKILL_DIRS: list[str] = _load_external_skill_dirs()
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_user_context.py tests/test_routing.py -v
```

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "refactor: remove USER_PERSONAS from config; persona loading moved to user_context"
```

---

## Task 5: Update `memory.py` — fix `user.username` reference

**Files:**
- Modify: `memory.py`

- [ ] **Step 1: Fix the attribute name in the warning log**

In `memory.py` line 16, change `user.username` to `user.user_id`:

```python
# Before
logger.warning("Failed to load history for %s: %s", user.username, e)

# After
logger.warning("Failed to load history for %s: %s", user.user_id, e)
```

The `load` and `save` functions already use `user.history_path` — no other changes needed.

- [ ] **Step 2: Run tests**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_user_context.py -v
```

Expected: All pass (history isolation test exercises load/save).

- [ ] **Step 3: Commit**

```bash
git add memory.py
git commit -m "fix: update memory.py log reference from user.username to user.user_id"
```

---

## Task 6: Update `agent.py`

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from config import AGENT_MODEL, MAX_TOKENS, MODE_PROMPTS, SOUL_CONTENT, SYSTEM_PROMPT, USER_PERSONAS
from user import User
```

With:
```python
from config import AGENT_MODEL, MAX_TOKENS, MODE_PROMPTS, SOUL_CONTENT, SYSTEM_PROMPT
from user_context import UserContext
```

- [ ] **Step 2: Update `build_system_prompt`**

Replace the entire `build_system_prompt` function:

```python
def build_system_prompt(
    user: "UserContext | None",
    mode: str,
    skill_name: str | None,
    skill_instructions: str | None,
) -> str:
    parts = [SYSTEM_PROMPT]
    if SOUL_CONTENT:
        parts.append(f"\n## Identity\n{SOUL_CONTENT}")
    if user is not None:
        user_section = f"\n## User\nName: {user.display_name}"
        if user.persona:
            user_section += f"\n\n{user.persona}"
        parts.append(user_section)
        if user.cross_channel_summary:
            parts.append(f"\n{user.cross_channel_summary}")
    parts.append(f"\n## Mode\n{MODE_PROMPTS[mode]}")
    if skill_instructions:
        parts.append(f"\n## Active skill: {skill_name}\n\n{skill_instructions}")
    return "\n".join(parts)
```

- [ ] **Step 3: Update `run` function type annotation**

Change:
```python
def run(
    history: list[dict],
    user: User | None,
    mode: Literal["command", "chat"],
) -> tuple[str, str | None, list[str]]:
```

To:
```python
def run(
    history: list[dict],
    user: "UserContext | None",
    mode: Literal["command", "chat"],
) -> tuple[str, str | None, list[str]]:
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_user_context.py tests/test_routing.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add agent.py
git commit -m "feat: wire UserContext into agent — inject persona and cross-channel summary"
```

---

## Task 7: Write tests for `messaging.py`, then create it

**Files:**
- Create: `tests/test_messaging.py`
- Create: `messaging.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_messaging.py`:

```python
"""Tests for central message dispatch."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from user_context import UserContext


def _make_ctx(tmp_path, channel="telegram", channel_id="12345"):
    return UserContext(
        user_id="bob",
        display_name="Bob",
        persona="Bob prefers direct, short messages.",
        active_channel=channel,
        channels={channel: channel_id},
        history_path=tmp_path / "users" / "bob" / channel / "history.json",
        cross_channel_summary="",
        is_anonymous=False,
    )


def test_send_message_telegram_logs_to_history(tmp_path, monkeypatch):
    """send_message sends via Telegram and logs the adapted message to recipient's history."""
    import messaging
    import memory
    import skills.telegram as tg

    recipient = _make_ctx(tmp_path)
    monkeypatch.setattr(messaging, "_adapt_to_persona", lambda draft, persona: f"adapted: {draft}")
    monkeypatch.setattr(tg, "send_message", lambda chat_id, text: True)

    result = messaging.send_message(recipient, "hello there")

    assert "sent" in result.lower()
    hist = memory.load(recipient)
    assert len(hist) == 1
    assert hist[0]["role"] == "assistant"
    assert hist[0]["content"] == "adapted: hello there"


def test_send_message_no_channel_returns_error(tmp_path):
    """send_message returns an error string when no channel ID is available."""
    import messaging

    recipient = UserContext(
        user_id="ghost",
        display_name="Ghost",
        persona="",
        active_channel="cli",
        channels={},
        history_path=tmp_path / "users" / "ghost" / "cli" / "history.json",
        cross_channel_summary="",
        is_anonymous=True,
    )

    result = messaging.send_message(recipient, "hello")
    assert "no channel configured" in result.lower()


def test_send_message_slack_logs_to_history(tmp_path, monkeypatch):
    """send_message routes to Slack DM and logs to history."""
    import messaging
    import memory
    import skills.slack as slack

    recipient = _make_ctx(tmp_path, channel="slack", channel_id="UBOB")
    monkeypatch.setattr(messaging, "_adapt_to_persona", lambda draft, persona: draft)
    monkeypatch.setattr(slack, "send_slack_dm", lambda user_id, text: "ts123")

    result = messaging.send_message(recipient, "hey bob")

    assert "sent" in result.lower()
    hist = memory.load(recipient)
    assert hist[-1]["content"] == "hey bob"


def test_adapt_to_persona_fallback_on_error(monkeypatch):
    """_adapt_to_persona returns original draft when Anthropic call fails."""
    import messaging

    def _fail_create(*args, **kwargs):
        raise RuntimeError("API unavailable")

    import anthropic
    monkeypatch.setattr(anthropic.Anthropic, "__init__", lambda self: None)

    class FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("API unavailable")

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(messaging.anthropic, "Anthropic", lambda: FakeClient())

    result = messaging._adapt_to_persona("original text", "some persona")
    assert result == "original text"


def test_preferred_channel_order(tmp_path, monkeypatch):
    """When active_channel has no ID, send_message falls back to preferred channel order."""
    import messaging
    import skills.telegram as tg

    recipient = UserContext(
        user_id="carol",
        display_name="Carol",
        persona="",
        active_channel="cli",  # cli has no channel_id in channels dict
        channels={"telegram": "99999", "slack": "UCAROL"},
        history_path=tmp_path / "users" / "carol" / "cli" / "history.json",
        cross_channel_summary="",
        is_anonymous=False,
    )

    monkeypatch.setattr(messaging, "_adapt_to_persona", lambda draft, persona: draft)
    sent = []
    monkeypatch.setattr(tg, "send_message", lambda chat_id, text: sent.append(chat_id) or True)

    messaging.send_message(recipient, "hi")
    assert sent == ["99999"]  # telegram preferred over slack
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_messaging.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'messaging'`

- [ ] **Step 3: Create `messaging.py`**

```python
import logging

import anthropic

from config import AGENT_MODEL
from user_context import UserContext

logger = logging.getLogger(__name__)

_PREFERRED_CHANNELS = ["telegram", "slack", "email"]


def _get_send_target(recipient: UserContext) -> "tuple[str, str] | None":
    """Return (channel_name, channel_id) to send to.

    Uses recipient.active_channel if it has a configured ID, otherwise
    falls through preferred channel order: telegram → slack → email.
    """
    active_id = recipient.channels.get(recipient.active_channel)
    if active_id:
        return (recipient.active_channel, str(active_id))
    for ch in _PREFERRED_CHANNELS:
        ch_id = recipient.channels.get(ch)
        if ch_id:
            return (ch, str(ch_id))
    return None


def _adapt_to_persona(draft: str, persona: str) -> str:
    """Adapt the draft message tone/style using the recipient's persona via Opus.

    Returns the original draft unchanged if the API call fails.
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=500,
            system=(
                "You are adapting a message to be delivered to a specific person. "
                "Rewrite the message to match their communication style and preferences. "
                "Output only the rewritten message text, nothing else.\n\n"
                f"{persona}"
            ),
            messages=[{"role": "user", "content": draft}],
        )
        return response.content[0].text
    except Exception as e:
        logger.warning("Persona adaptation failed, using original draft: %s", e)
        return draft


def send_message(recipient: UserContext, draft: str) -> str:
    """
    Central dispatch for all agent-initiated outbound messages.

    Steps:
    1. Adapts tone/style using recipient's persona (Opus call).
    2. Routes to recipient's channel (telegram, slack, etc.).
    3. Logs the sent message to recipient's channel history.

    Returns a human-readable confirmation string.
    This function is NOT called for inline session replies — those go through
    the normal agent return path where the persona is already in the system prompt.
    """
    import memory as memory_module

    adapted = _adapt_to_persona(draft, recipient.persona)

    target = _get_send_target(recipient)
    if target is None:
        return f"Cannot send to {recipient.display_name}: no channel configured."

    channel_name, channel_id = target
    ok = False

    if channel_name == "telegram":
        from skills.telegram import send_message as _telegram_send
        ok = _telegram_send(channel_id, adapted)
    elif channel_name == "slack":
        from skills.slack import send_slack_dm
        result = send_slack_dm(channel_id, adapted)
        ok = not str(result).startswith("Error")
    else:
        return f"Channel '{channel_name}' send not yet implemented."

    if not ok:
        return f"Failed to send message to {recipient.display_name} via {channel_name}."

    hist = memory_module.load(recipient)
    hist.append({"role": "assistant", "content": adapted})
    memory_module.save(hist, recipient)

    return f"Message sent to {recipient.display_name} via {channel_name}."
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/test_messaging.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add messaging.py tests/test_messaging.py
git commit -m "feat: add messaging.py — central dispatch with persona adaptation and history logging"
```

---

## Task 8: Update `server.py`

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Update the import line**

Replace:
```python
from user import load_user, load_user_by_telegram_chat_id
```

With:
```python
from user_context import load_user_context, load_user_context_by_id
```

- [ ] **Step 2: Update the Telegram webhook handler**

Replace the current user lookup block in `webhook_telegram` (lines 276–279):

```python
user = load_user_by_telegram_chat_id(chat_id)
if user is None:
    logger.warning("Unknown Telegram chat_id: %r", chat_id)
    return {"status": "ignored", "reason": "unknown chat_id"}
```

With:

```python
user = load_user_context("telegram", chat_id)
if user.is_anonymous:
    logger.info("Anonymous Telegram user: chat_id=%r, assigned user_id=%r", chat_id, user.user_id)
```

- [ ] **Step 3: Update the capture endpoint**

Replace:
```python
try:
    user = load_user(username)
except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
```

With:
```python
try:
    user = load_user_context_by_id(username)
except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
```

Also update the Telegram confirmation send inside `_run_capture`. Replace:

```python
if response_text and user.telegram_chat_id:
    ok = telegram_send(user.telegram_chat_id, response_text)
    logger.info("Capture telegram send to %s: %s", user.telegram_chat_id, "ok" if ok else "failed")
else:
    logger.warning("Capture: no telegram_chat_id for user %s or empty response", username)
```

With:

```python
telegram_chat_id = user.channels.get("telegram", "")
if response_text and telegram_chat_id:
    ok = telegram_send(telegram_chat_id, response_text)
    logger.info("Capture telegram send to %s: %s", telegram_chat_id, "ok" if ok else "failed")
else:
    logger.warning("Capture: no telegram channel for user %s or empty response", username)
```

- [ ] **Step 4: Verify server imports cleanly**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -c "import server; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: update server.py to use UserContext; anonymous Telegram users now get a context"
```

---

## Task 9: Update `run.py`

**Files:**
- Modify: `run.py`

- [ ] **Step 1: Update import and user loading**

Replace:
```python
from user import load_user
```

With:
```python
from user_context import load_user_context_by_id
```

Replace:
```python
user = load_user(args.user)
```

With:
```python
user = load_user_context_by_id(args.user)
```

- [ ] **Step 2: Verify CLI starts cleanly (dry run)**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -c "import run; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add run.py
git commit -m "feat: update run.py to use load_user_context_by_id"
```

---

## Task 10: Update `skills/telegram/__init__.py`

**Files:**
- Modify: `skills/telegram/__init__.py`

- [ ] **Step 1: Update `lookup_telegram_recipient`**

The function currently uses `entry.get("telegram_chat_id")` and `USER_PERSONAS`. Replace the entire `lookup_telegram_recipient` function:

```python
@register
def lookup_telegram_recipient(name: str) -> str:
    """Look up a user by name or user ID to get their Telegram chat ID and persona.
    Returns a JSON object with 'chat_id' and 'persona' so you can draft a message
    tailored to the recipient before sending. Call this before send_telegram_message
    whenever messaging another user.
    """
    from config import _CONFIG
    from user_context import _load_persona

    name_lower = name.strip().lower()
    for entry in _CONFIG.get("users", []):
        user_id = entry.get("id", "")
        display_name = entry.get("name", "")
        if name_lower == user_id.lower() or name_lower == display_name.lower():
            channels = entry.get("channels", {})
            chat_id = channels.get("telegram")
            if not chat_id:
                return json.dumps({"error": f"User '{display_name}' has no Telegram chat ID configured."})
            persona = _load_persona(entry.get("persona_url"))
            return json.dumps({
                "chat_id": str(chat_id),
                "user_id": user_id,
                "name": display_name,
                "persona": persona,
            })

    known = [e.get("name") or e.get("id") for e in _CONFIG.get("users", []) if e.get("id")]
    return json.dumps({"error": f"No user found matching '{name}'. Known users: {known}"})
```

- [ ] **Step 2: Verify the telegram skill loads cleanly**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -c "from skills.telegram import lookup_telegram_recipient; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add skills/telegram/__init__.py
git commit -m "feat: update telegram skill to use channels dict and _load_persona"
```

---

## Task 11: Update `test_command_mode.py`, delete `user.py`, run full suite

**Files:**
- Modify: `tests/test_command_mode.py`
- Delete: `user.py`
- Delete: `tests/test_users.py`

- [ ] **Step 1: Update `test_command_mode.py` fixture**

The fixture imports `User` from `user.py` and patches `server.load_user`. Update it to use `UserContext` and patch `server.load_user_context_by_id`:

Replace the `client` fixture:

```python
@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a TestClient with isolated user storage."""
    from user_context import UserContext, USERNAME_RE

    def fake_load_user_context_by_id(username, channel="cli"):
        if not USERNAME_RE.match(username):
            raise ValueError(f"Invalid username {username!r}")
        return UserContext(
            user_id=username,
            display_name=username.capitalize(),
            persona="",
            active_channel=channel,
            channels={},
            history_path=tmp_path / username / channel / "history.json",
            cross_channel_summary="",
            is_anonymous=False,
        )

    monkeypatch.setattr("server.load_user_context_by_id", fake_load_user_context_by_id)
    monkeypatch.setattr("server.memory.load", lambda user: [])
    monkeypatch.setattr("server.memory.save", lambda hist, user: None)

    from fastapi.testclient import TestClient
    import server
    return TestClient(server.app)
```

Remove the top-level imports of `user` and `User` from that file.

- [ ] **Step 2: Delete `user.py` and `tests/test_users.py`**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && rm user.py tests/test_users.py
```

- [ ] **Step 3: Run the full test suite**

```bash
cd /Users/dustinmcbride/git/office_of_tim_fish/assistant && python -m pytest tests/ -v
```

Expected results:
- `test_user_context.py` — all pass
- `test_messaging.py` — all pass
- `test_routing.py` — all pass
- `test_skills.py` — all pass
- `test_trello.py` — all pass
- `test_command_mode.py` — `test_health` passes; `test_command_*` tests return 404 (the `/command` endpoint is not implemented — this is pre-existing, not a regression)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: remove user.py — fully replaced by user_context.py"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `UserContext` dataclass with all fields | Task 3 |
| `load_user_context(channel, channel_id)` with anonymous fallback | Task 3 |
| `load_user_context_by_id(user_id, channel)` for CLI | Task 3 |
| `channels` dict in config.json | Task 1 |
| Per-user, per-channel memory path | Task 3 (history_path structure) |
| `build_cross_channel_summary` — last 5 turns, Opus summarization | Task 3 |
| Cross-channel summary injected into system prompt | Task 6 |
| `messaging.py` — persona adaptation, channel routing, history logging | Task 7 |
| Preferred channel order (telegram → slack → email) | Task 7 |
| Telegram webhook uses `load_user_context` | Task 8 |
| Capture endpoint uses `load_user_context_by_id` | Task 8 |
| `run.py` uses `load_user_context_by_id` | Task 9 |
| `lookup_telegram_recipient` updated to channels dict | Task 10 |
| `USER_PERSONAS` removed from config | Task 4 |
| `user.py` deleted | Task 11 |

All spec requirements covered. No gaps found.
