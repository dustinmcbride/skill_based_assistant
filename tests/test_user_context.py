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
    ctx = load_user_context("unknown_channel", "00000")
    assert ctx.persona == DEFAULT_PERSONA


def test_memory_trim():
    """Trim keeps last N complete user turns."""
    import memory
    hist = []
    for i in range(50):
        hist.append({"role": "user", "content": f"msg {i}"})
        hist.append({"role": "assistant", "content": f"resp {i}"})
    trimmed = memory.trim(hist, max_turns=10)
    user_msgs = [m for m in trimmed if m["role"] == "user"]
    assert len(user_msgs) == 10
    assert trimmed[0]["role"] == "user"
