"""Tests for user loading and history isolation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import user as user_module


def test_load_user_invalid_username():
    with pytest.raises(ValueError):
        user_module.load_user("../etc/passwd")

    with pytest.raises(ValueError):
        user_module.load_user("UPPER")

    with pytest.raises(ValueError):
        user_module.load_user("has space")

    with pytest.raises(ValueError):
        user_module.load_user("has/slash")


def test_load_user_valid_names():
    valid = ["tim", "tina", "user-123", "a", "abc-def-ghi"]
    for name in valid:
        assert user_module.USERNAME_RE.match(name), f"{name!r} should be valid"


def test_history_isolation(tmp_path, monkeypatch):
    import memory

    from user import User

    def make_user(username):
        return User(
            username=username,
            display_name=username.capitalize(),
            history_path=tmp_path / username / "history.json",
        )

    alice = make_user("alice")
    bob = make_user("bob")

    memory.save([{"role": "user", "content": "hello from alice"}], alice)
    memory.save([{"role": "user", "content": "hello from bob"}], bob)

    alice_hist = memory.load(alice)
    bob_hist = memory.load(bob)

    assert alice_hist[0]["content"] == "hello from alice"
    assert bob_hist[0]["content"] == "hello from bob"
    assert alice_hist != bob_hist


def test_memory_trim():
    import memory

    hist = []
    for i in range(50):
        hist.append({"role": "user", "content": f"msg {i}"})
        hist.append({"role": "assistant", "content": f"resp {i}"})

    trimmed = memory.trim(hist, max_turns=10)
    user_msgs = [m for m in trimmed if m["role"] == "user"]
    assert len(user_msgs) == 10
    assert trimmed[0]["role"] == "user"
