"""
Trello skill.

Boards, lists, and cards are cached locally to minimise API calls and token usage.
The cache auto-refreshes when stale (default TTL: 5 minutes).

Required env vars:
    TRELLO_API_KEY   — from https://trello.com/power-ups/admin
    TRELLO_TOKEN     — from https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token&key=<API_KEY>
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from skills import register

_API_KEY = os.environ.get("TRELLO_API_KEY", "")
_TOKEN = os.environ.get("TRELLO_TOKEN", "")
from config import ASSISTANT_DIR
_CACHE_FILE = ASSISTANT_DIR / "trello_cache.json"
_CACHE_TTL_SECONDS = 300  # 5 minutes
_MAX_CARDS_PER_LIST = 50


# ── API helpers ───────────────────────────────────────────────────────────────

def _auth_params() -> str:
    return f"key={urllib.parse.quote(_API_KEY)}&token={urllib.parse.quote(_TOKEN)}"


def _get(path: str, params: str = "") -> dict | list:
    if not _API_KEY or not _TOKEN:
        raise RuntimeError(
            "TRELLO_API_KEY and TRELLO_TOKEN are not set. "
            "Add them to your .env file."
        )
    sep = "&" if params else ""
    url = f"https://api.trello.com/1{path}?{_auth_params()}{sep}{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _post(path: str, data: dict) -> dict:
    if not _API_KEY or not _TOKEN:
        raise RuntimeError("TRELLO_API_KEY and TRELLO_TOKEN are not set.")
    url = f"https://api.trello.com/1{path}?{_auth_params()}"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _put(path: str, data: dict) -> dict:
    if not _API_KEY or not _TOKEN:
        raise RuntimeError("TRELLO_API_KEY and TRELLO_TOKEN are not set.")
    url = f"https://api.trello.com/1{path}?{_auth_params()}"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    if not _CACHE_FILE.exists():
        return False
    try:
        data = json.loads(_CACHE_FILE.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        return age < _CACHE_TTL_SECONDS
    except Exception:
        return False


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, indent=2))


def _fetch_and_cache() -> dict:
    """Fetch all open boards with their lists and cards from the Trello API."""
    boards_raw = _get("/members/me/boards", "filter=open&fields=id,name")
    boards = []
    for b in boards_raw:
        lists_raw = _get(f"/boards/{b['id']}/lists", "filter=open&fields=id,name")
        lists = []
        for lst in lists_raw:
            cards_raw = _get(
                f"/lists/{lst['id']}/cards",
                f"limit={_MAX_CARDS_PER_LIST}&fields=id,name,desc,due,labels",
            )
            cards = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "desc": c["desc"][:200] if c.get("desc") else "",
                    "due": c.get("due"),
                    "labels": [lb["name"] for lb in c.get("labels", []) if lb.get("name")],
                }
                for c in cards_raw
            ]
            lists.append({"id": lst["id"], "name": lst["name"], "cards": cards})
        boards.append({"id": b["id"], "name": b["name"], "lists": lists})

    cache = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "boards": boards,
    }
    _save_cache(cache)
    return cache


def _get_cache() -> dict:
    """Return cache, refreshing from API if stale."""
    if _cache_is_fresh():
        return _load_cache()
    return _fetch_and_cache()


def _compact_overview(cache: dict) -> str:
    """Render cache as a compact text summary for the agent."""
    lines = []
    for board in cache.get("boards", []):
        lines.append(f"Board: {board['name']} (id:{board['id']})")
        for lst in board.get("lists", []):
            lines.append(f"  List: {lst['name']} (id:{lst['id']})")
            for card in lst.get("cards", []):
                due = f" [due:{card['due'][:10]}]" if card.get("due") else ""
                labels = f" [{','.join(card['labels'])}]" if card.get("labels") else ""
                desc = f" — {card['desc']}" if card.get("desc") else ""
                lines.append(f"    • {card['name']}{due}{labels} (id:{card['id']}){desc}")
    return "\n".join(lines) if lines else "No open boards found."


# ── Skills ────────────────────────────────────────────────────────────────────

@register
def trello_overview() -> str:
    """
    Return a compact summary of all open Trello boards, lists, and cards.
    Uses a local cache (refreshed every 5 minutes) to avoid redundant API calls.
    Call this first to get board/list/card IDs before any write operation.
    """
    try:
        cache = _get_cache()
        fetched_at = cache.get("fetched_at", "unknown")[:19].replace("T", " ")
        return f"(cached at {fetched_at} UTC)\n\n{_compact_overview(cache)}"
    except Exception as e:
        return f"Error fetching Trello overview: {e}"


@register
def trello_create_card(list_id: str, name: str, desc: str = "", due: str = "") -> str:
    """
    Create a new Trello card in the specified list.

    Args:
        list_id: ID of the target list (from trello_overview)
        name: Card title
        desc: Optional card description
        due: Optional due date in ISO 8601 format (e.g. 2024-03-15T09:00:00)
    """
    try:
        data: dict = {"idList": list_id, "name": name}
        if desc:
            data["desc"] = desc
        if due:
            data["due"] = due
        card = _post("/cards", data)

        # Update cache inline
        cache = _load_cache()
        for board in cache.get("boards", []):
            for lst in board.get("lists", []):
                if lst["id"] == list_id:
                    lst["cards"].append({
                        "id": card["id"],
                        "name": name,
                        "desc": desc[:200],
                        "due": due or None,
                        "labels": [],
                    })
                    _save_cache(cache)
                    return f"Created card '{name}' in list '{lst['name']}' on board '{board['name']}' (id:{card['id']})"
        _save_cache(cache)
        return f"Created card '{name}' (id:{card['id']})"
    except Exception as e:
        return f"Error creating card: {e}"


@register
def trello_move_card(card_id: str, list_id: str) -> str:
    """
    Move a Trello card to a different list.

    Args:
        card_id: ID of the card to move (from trello_overview)
        list_id: ID of the destination list (from trello_overview)
    """
    try:
        _put(f"/cards/{card_id}", {"idList": list_id})

        # Update cache inline
        cache = _load_cache()
        card_data = None
        for board in cache.get("boards", []):
            for lst in board.get("lists", []):
                for card in lst["cards"]:
                    if card["id"] == card_id:
                        card_data = card
                        lst["cards"].remove(card)
                        break

        dest_list_name = "unknown list"
        dest_board_name = ""
        if card_data:
            for board in cache.get("boards", []):
                for lst in board.get("lists", []):
                    if lst["id"] == list_id:
                        lst["cards"].append(card_data)
                        dest_list_name = lst["name"]
                        dest_board_name = f" on {board['name']}"
                        break
            _save_cache(cache)

        card_name = card_data["name"] if card_data else card_id
        return f"Moved '{card_name}' to '{dest_list_name}'{dest_board_name}."
    except Exception as e:
        return f"Error moving card: {e}"


@register
def trello_update_card(card_id: str, name: str = "", desc: str = "", due: str = "") -> str:
    """
    Update the name, description, or due date of a Trello card.
    Only fields with non-empty values are updated.

    Args:
        card_id: ID of the card to update (from trello_overview)
        name: New card title (leave empty to keep current)
        desc: New description (leave empty to keep current)
        due: New due date in ISO 8601 format (leave empty to keep current)
    """
    try:
        data = {}
        if name:
            data["name"] = name
        if desc:
            data["desc"] = desc
        if due:
            data["due"] = due
        if not data:
            return "Nothing to update — provide at least one of: name, desc, due."
        _put(f"/cards/{card_id}", data)

        # Update cache inline
        cache = _load_cache()
        for board in cache.get("boards", []):
            for lst in board.get("lists", []):
                for card in lst["cards"]:
                    if card["id"] == card_id:
                        if name:
                            card["name"] = name
                        if desc:
                            card["desc"] = desc[:200]
                        if due:
                            card["due"] = due
                        _save_cache(cache)
                        return f"Updated card '{card['name']}'."
        _save_cache(cache)
        return f"Updated card {card_id}."
    except Exception as e:
        return f"Error updating card: {e}"


@register
def trello_archive_card(card_id: str) -> str:
    """
    Archive (close) a Trello card by its ID.

    Args:
        card_id: ID of the card to archive (from trello_overview)
    """
    try:
        _put(f"/cards/{card_id}", {"closed": "true"})

        # Remove from cache inline
        cache = _load_cache()
        card_name = card_id
        for board in cache.get("boards", []):
            for lst in board.get("lists", []):
                for card in lst["cards"]:
                    if card["id"] == card_id:
                        card_name = card["name"]
                        lst["cards"].remove(card)
                        _save_cache(cache)
                        return f"Archived '{card_name}'."
        return f"Archived card {card_id} (not found in cache)."
    except Exception as e:
        return f"Error archiving card: {e}"


@register
def trello_refresh_cache() -> str:
    """
    Force a full refresh of the Trello cache from the API.
    Use this if the board state seems stale or out of sync.
    """
    try:
        cache = _fetch_and_cache()
        board_count = len(cache.get("boards", []))
        card_count = sum(
            len(card)
            for b in cache["boards"]
            for lst in b["lists"]
            for card in [lst["cards"]]
        )
        return f"Cache refreshed: {board_count} board(s), {card_count} card(s) indexed."
    except Exception as e:
        return f"Error refreshing cache: {e}"
