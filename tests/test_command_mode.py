"""Tests for the command mode FastAPI endpoint."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


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


def _mock_agent_run(response_text="Done.", skill=None, actions=None):
    return MagicMock(return_value=(response_text, skill, actions or []))


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.xfail(reason="/command endpoint not yet implemented", strict=True)
def test_command_returns_200(client):
    with patch("server.agent.run", _mock_agent_run("Added to your calendar.")):
        resp = client.post("/command/tim", json={"message": "add dentist appointment tomorrow"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert data["response"] == "Added to your calendar."


@pytest.mark.xfail(reason="/command endpoint not yet implemented", strict=True)
def test_command_includes_skill_and_actions(client):
    with patch("server.agent.run", _mock_agent_run("Done.", skill="calendar", actions=["create_event"])):
        resp = client.post("/command/tim", json={"message": "schedule a meeting"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill"] == "calendar"
    assert "create_event" in data["actions_taken"]


def test_command_invalid_username(client):
    resp = client.post("/command/INVALID_USER", json={"message": "hello"})
    assert resp.status_code == 404


@pytest.mark.xfail(reason="/command endpoint not yet implemented", strict=True)
def test_command_malformed_body(client):
    resp = client.post("/command/tim", json={"wrong_field": "hello"})
    assert resp.status_code == 422


@pytest.mark.xfail(reason="/command endpoint not yet implemented", strict=True)
def test_command_mode_no_question(client):
    """Command mode responses must not end with a question."""
    with patch("server.agent.run", _mock_agent_run("I added the reminder for 9am tomorrow.")):
        resp = client.post("/command/tim", json={"message": "remind me to call dentist"})
    assert resp.status_code == 200
    response_text = resp.json()["response"]
    # Final sentence must not end with a question mark
    sentences = [s.strip() for s in response_text.replace("?", "?\n").splitlines() if s.strip()]
    if sentences:
        assert not sentences[-1].endswith("?"), (
            f"Command mode response ended with a question: {response_text!r}"
        )


@pytest.mark.xfail(reason="/command endpoint not yet implemented", strict=True)
def test_command_agent_error_returns_500(client):
    with patch("server.agent.run", side_effect=RuntimeError("model error")):
        resp = client.post("/command/tim", json={"message": "do something"})
    assert resp.status_code == 500
