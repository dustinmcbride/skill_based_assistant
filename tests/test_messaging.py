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
