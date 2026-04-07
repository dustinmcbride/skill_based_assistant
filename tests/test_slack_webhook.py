"""Tests for the Slack Events API webhook endpoint."""

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _sign_payload(secret: str, body: bytes) -> tuple[str, str]:
    """Return (timestamp, signature) for a Slack-signed request."""
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:".encode() + body
    sig = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return ts, sig


@pytest.fixture
def client(tmp_path, monkeypatch):
    from user_context import UserContext

    def fake_load_user_context(channel, channel_id):
        return UserContext(
            user_id="dustin",
            display_name="Dustin",
            persona="",
            active_channel=channel,
            channels={channel: channel_id},
            history_path=tmp_path / "dustin" / channel / "history.json",
            cross_channel_summary="",
            is_anonymous=False,
        )

    monkeypatch.setattr("server.load_user_context", fake_load_user_context)
    monkeypatch.setattr("server.memory.load", lambda user: [])
    monkeypatch.setattr("server.memory.save", lambda hist, user: None)
    # Clear dedup state between tests
    import server
    server._SEEN_SLACK_EVENT_IDS.clear()

    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _mention_payload(text="hello bot", channel="C123", user="U456", event_id="Ev001", ts="111.222"):
    return {
        "type": "event_callback",
        "event_id": event_id,
        "event": {
            "type": "app_mention",
            "user": user,
            "text": f"<@UBOT> {text}",
            "channel": channel,
            "ts": ts,
        },
    }


def test_url_verification(client):
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "abc123"


def test_app_mention_runs_agent_and_replies(client, monkeypatch):
    posted = []

    def fake_agent_run(hist, user, mode):
        return "Hello from agent!", "none", []

    def fake_chat_postMessage(**kwargs):
        posted.append(kwargs)
        return MagicMock()

    import server
    monkeypatch.setattr(server.agent, "run", fake_agent_run)

    import skills.slack as slack_skill
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", fake_chat_postMessage)

    body = json.dumps(_mention_payload(text="what time is it")).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert len(posted) == 1
    assert posted[0]["channel"] == "C123"
    assert posted[0]["text"] == "Hello from agent!"
    assert posted[0]["thread_ts"] == "111.222"


def test_app_mention_strips_bot_mention(client, monkeypatch):
    received_texts = []

    def fake_agent_run(hist, user, mode):
        received_texts.append(hist[-1]["content"])
        return "ok", "none", []

    import server
    import skills.slack as slack_skill
    monkeypatch.setattr(server.agent, "run", fake_agent_run)
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: MagicMock())

    body = json.dumps(_mention_payload(text="remind me about lunch")).encode()
    client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})

    assert len(received_texts) == 1
    assert "remind me about lunch" in received_texts[0]
    assert "C123" in received_texts[0]  # channel injected into preamble


def test_message_event_with_bot_mention_is_handled(client, monkeypatch):
    """A message event containing the bot's user ID is treated like an app_mention."""
    posted = []

    import skills.slack as slack_skill
    monkeypatch.setattr(slack_skill, "_bot_user_id", "UBOT")
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: posted.append(kw) or MagicMock())

    import server
    monkeypatch.setattr(server.agent, "run", lambda hist, user, mode: ("got it", "none", []))

    payload = {
        "type": "event_callback",
        "event_id": "Ev_msg",
        "event": {
            "type": "message",
            "user": "U456",
            "text": "<@UBOT> what is today?",
            "channel": "C123",
            "ts": "222.333",
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert len(posted) == 1


def test_message_event_without_bot_mention_runs_in_monitoring_mode(client, monkeypatch):
    """Messages with no bot mention are processed in monitoring mode (agent decides whether to reply)."""
    received_preambles = []

    import skills.slack as slack_skill
    import server
    monkeypatch.setattr(slack_skill, "_bot_user_id", "UBOT")
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: MagicMock())

    def fake_run(hist, user, mode):
        received_preambles.append(hist[-1]["content"])
        return "", "none", []  # agent says nothing — no consensus

    monkeypatch.setattr(server.agent, "run", fake_run)

    payload = {
        "type": "event_callback",
        "event_id": "Ev_mon",
        "event": {"type": "message", "user": "U456", "text": "hey @someone else", "channel": "C123", "ts": "1.1"},
    }
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.json()["status"] == "ok"
    assert "silently monitoring" in received_preambles[0]


def test_thread_reply_responded_to_when_bot_participated(client, monkeypatch):
    """A reply in a thread where the bot has previously replied is handled without a mention."""
    posted = []

    import skills.slack as slack_skill
    monkeypatch.setattr(slack_skill, "_bot_user_id", "UBOT")
    monkeypatch.setattr(slack_skill, "bot_participated_in_thread", lambda ch, ts, bot_id: True)
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: posted.append(kw) or MagicMock())

    import server
    monkeypatch.setattr(server.agent, "run", lambda hist, user, mode: ("sure thing", "none", []))

    payload = {
        "type": "event_callback",
        "event_id": "Ev_thread",
        "event": {
            "type": "message",
            "user": "U456",
            "text": "can you clarify that?",
            "channel": "C123",
            "ts": "333.444",
            "thread_ts": "111.222",
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert len(posted) == 1


def test_thread_reply_without_bot_runs_in_monitoring_mode(client, monkeypatch):
    """Thread replies where bot hasn't participated are processed in monitoring mode."""
    received_preambles = []

    import skills.slack as slack_skill
    import server
    monkeypatch.setattr(slack_skill, "_bot_user_id", "UBOT")
    monkeypatch.setattr(slack_skill, "bot_participated_in_thread", lambda ch, ts, bot_id: False)
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: MagicMock())

    def fake_run(hist, user, mode):
        received_preambles.append(hist[-1]["content"])
        return "", "none", []

    monkeypatch.setattr(server.agent, "run", fake_run)

    payload = {
        "type": "event_callback",
        "event_id": "Ev_mon2",
        "event": {
            "type": "message",
            "user": "U456",
            "text": "just chatting here",
            "channel": "C123",
            "ts": "333.444",
            "thread_ts": "111.222",
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.json()["status"] == "ok"
    assert "silently monitoring" in received_preambles[0]


def test_bot_own_message_ignored(client, monkeypatch):
    """Messages from the bot itself are never processed."""
    import skills.slack as slack_skill
    monkeypatch.setattr(slack_skill, "_bot_user_id", "UBOT")

    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "UBOT",   # same as bot_user_id
            "text": "<@UBOT> I just replied",
            "channel": "C123",
            "ts": "1.1",
        },
    }
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.json()["reason"] == "bot or subtype"


def test_non_app_mention_ignored(client):
    payload = {"type": "event_callback", "event": {"type": "message", "text": "hi"}}
    body = json.dumps(payload).encode()
    resp = client.post("/webhook/slack", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_duplicate_event_ignored(client, monkeypatch):
    calls = []

    def fake_agent_run(hist, user, mode):
        calls.append(1)
        return "ok", "none", []

    import server
    import skills.slack as slack_skill
    monkeypatch.setattr(server.agent, "run", fake_agent_run)
    monkeypatch.setattr(slack_skill.client, "chat_postMessage", lambda **kw: MagicMock())

    body = json.dumps(_mention_payload(event_id="Ev_dup")).encode()
    headers = {"Content-Type": "application/json"}
    client.post("/webhook/slack", content=body, headers=headers)
    resp = client.post("/webhook/slack", content=body, headers=headers)

    assert resp.json()["reason"] == "duplicate"
    assert len(calls) == 1


def test_signature_verification_rejects_bad_sig(monkeypatch):
    import server
    monkeypatch.setattr(server, "_SLACK_SIGNING_SECRET", "mysecret")
    server._SEEN_SLACK_EVENT_IDS.clear()

    from fastapi.testclient import TestClient
    tc = TestClient(server.app)

    body = json.dumps(_mention_payload()).encode()
    resp = tc.post(
        "/webhook/slack",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=badsignature",
        },
    )
    assert resp.status_code == 401


def test_signature_verification_accepts_valid_sig(monkeypatch):
    import server
    secret = "mysecret"
    monkeypatch.setattr(server, "_SLACK_SIGNING_SECRET", secret)
    server._SEEN_SLACK_EVENT_IDS.clear()

    from fastapi.testclient import TestClient
    tc = TestClient(server.app)

    body = json.dumps({"type": "url_verification", "challenge": "xyz"}).encode()
    ts, sig = _sign_payload(secret, body)
    resp = tc.post(
        "/webhook/slack",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "xyz"
