"""Tests for skill routing — mocks the Anthropic API call."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure assistant/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import skill_loader


def _make_response(text: str):
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def test_select_skill_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_loader, "_skills_dir", lambda: Path(__file__).parent.parent / "skills")
    with patch("skill_loader.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _make_response("calendar")
        result = skill_loader.select_skill("remind me about my dentist appointment tomorrow")
    assert result == "calendar"


def test_select_skill_none(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_loader, "_skills_dir", lambda: Path(__file__).parent.parent / "skills")
    with patch("skill_loader.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _make_response("none")
        result = skill_loader.select_skill("what is the meaning of life")
    assert result is None


def test_select_skill_unknown_domain(monkeypatch):
    monkeypatch.setattr(skill_loader, "_skills_dir", lambda: Path(__file__).parent.parent / "skills")
    with patch("skill_loader.anthropic.Anthropic") as MockClient:
        # Router returns a domain name not in the discovered skills
        MockClient.return_value.messages.create.return_value = _make_response("unicorn")
        result = skill_loader.select_skill("some message")
    assert result is None


def test_discover_skills():
    skills = skill_loader.discover_skills()
    # Should find at least these domains
    for domain in ("filesystem", "web", "calendar", "notes", "homelab"):
        assert domain in skills, f"Expected domain '{domain}' in discovered skills"
        assert isinstance(skills[domain], str)
        assert len(skills[domain]) > 0


def test_load_skill_instructions_exists():
    instructions = skill_loader.load_skill_instructions("filesystem")
    assert instructions is not None
    assert "filesystem" in instructions.lower() or "file" in instructions.lower()


def test_load_skill_instructions_missing():
    instructions = skill_loader.load_skill_instructions("nonexistent_skill_xyz")
    assert instructions is None
