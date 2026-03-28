"""Tests for the Trello skill — all API calls mocked."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import skills.trello.trello as trello


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_CACHE = {
    "fetched_at": "2024-01-01T00:00:00+00:00",
    "boards": [
        {
            "id": "board1",
            "name": "Web App",
            "lists": [
                {
                    "id": "list1",
                    "name": "To Do",
                    "cards": [
                        {"id": "card1", "name": "Fix login bug", "desc": "", "due": None, "labels": []},
                    ],
                },
                {
                    "id": "list2",
                    "name": "In Progress",
                    "cards": [],
                },
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "trello_cache.json"
    monkeypatch.setattr(trello, "_CACHE_FILE", cache_file)
    monkeypatch.setenv("TRELLO_API_KEY", "fake-key")
    monkeypatch.setenv("TRELLO_TOKEN", "fake-token")


def _write_cache(tmp_path_fixture=None):
    trello._CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    trello._CACHE_FILE.write_text(json.dumps(FAKE_CACHE))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_overview_uses_cache_when_fresh():
    _write_cache()
    # Patch _cache_is_fresh to return True so no API call is made
    with patch.object(trello, "_cache_is_fresh", return_value=True):
        result = trello.trello_overview()
    assert "Web App" in result
    assert "To Do" in result
    assert "Fix login bug" in result
    assert "card1" in result


def test_overview_refreshes_stale_cache():
    _write_cache()
    with patch.object(trello, "_cache_is_fresh", return_value=False), \
         patch.object(trello, "_fetch_and_cache", return_value=FAKE_CACHE) as mock_fetch:
        result = trello.trello_overview()
    mock_fetch.assert_called_once()
    assert "Web App" in result


def test_create_card_updates_cache():
    _write_cache()
    with patch.object(trello, "_cache_is_fresh", return_value=True), \
         patch.object(trello, "_post", return_value={"id": "card_new", "name": "New task"}):
        result = trello.trello_create_card(list_id="list1", name="New task", desc="Details")

    assert "New task" in result
    assert "card_new" in result
    # Cache should now contain the new card
    cache = json.loads(trello._CACHE_FILE.read_text())
    card_names = [
        c["name"]
        for b in cache["boards"]
        for lst in b["lists"]
        for c in lst["cards"]
    ]
    assert "New task" in card_names


def test_move_card_updates_cache():
    _write_cache()
    with patch.object(trello, "_put", return_value={}):
        result = trello.trello_move_card(card_id="card1", list_id="list2")

    assert "Fix login bug" in result
    assert "In Progress" in result
    # Verify card moved in cache
    cache = json.loads(trello._CACHE_FILE.read_text())
    todo_cards = next(
        lst["cards"] for b in cache["boards"] for lst in b["lists"] if lst["id"] == "list1"
    )
    in_progress_cards = next(
        lst["cards"] for b in cache["boards"] for lst in b["lists"] if lst["id"] == "list2"
    )
    assert not any(c["id"] == "card1" for c in todo_cards)
    assert any(c["id"] == "card1" for c in in_progress_cards)


def test_archive_card_removes_from_cache():
    _write_cache()
    with patch.object(trello, "_put", return_value={}):
        result = trello.trello_archive_card(card_id="card1")

    assert "Fix login bug" in result
    cache = json.loads(trello._CACHE_FILE.read_text())
    all_cards = [c for b in cache["boards"] for lst in b["lists"] for c in lst["cards"]]
    assert not any(c["id"] == "card1" for c in all_cards)


def test_update_card_patches_cache():
    _write_cache()
    with patch.object(trello, "_put", return_value={}):
        result = trello.trello_update_card(card_id="card1", name="Fix login bug (v2)")

    assert "Fix login bug (v2)" in result
    cache = json.loads(trello._CACHE_FILE.read_text())
    card = next(
        c for b in cache["boards"] for lst in b["lists"] for c in lst["cards"] if c["id"] == "card1"
    )
    assert card["name"] == "Fix login bug (v2)"


def test_update_card_no_fields():
    _write_cache()
    result = trello.trello_update_card(card_id="card1")
    assert "nothing to update" in result.lower()


def test_refresh_cache():
    _write_cache()
    with patch.object(trello, "_fetch_and_cache", return_value=FAKE_CACHE) as mock_fetch:
        result = trello.trello_refresh_cache()
    mock_fetch.assert_called_once()
    assert "refreshed" in result.lower()


def test_missing_credentials(monkeypatch):
    monkeypatch.setattr(trello, "_API_KEY", "")
    monkeypatch.setattr(trello, "_TOKEN", "")
    result = trello.trello_overview()
    assert "error" in result.lower()


def test_trello_tools_registered():
    from skills import get_tools
    tools = get_tools()
    names = [t["name"] for t in tools]
    for expected in (
        "trello_overview",
        "trello_create_card",
        "trello_move_card",
        "trello_update_card",
        "trello_archive_card",
        "trello_refresh_cache",
    ):
        assert expected in names, f"Expected tool '{expected}' not found"
