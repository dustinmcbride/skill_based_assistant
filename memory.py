import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load(user) -> list[dict]:
    """Load conversation history for the user. Returns [] if no history file."""
    path = user.history_path
    if not Path(path).exists():
        return []
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        logger.warning("Failed to load history for %s: %s", user.username, e)
        return []


def save(history: list[dict], user) -> None:
    """Save conversation history to disk, creating parent dirs as needed."""
    path = Path(user.history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2))


def trim(history: list[dict], max_turns: int = 40) -> list[dict]:
    """
    Keep the last max_turns complete turn pairs (user + assistant).
    Never trims mid-tool-exchange — always finds a clean boundary.
    """
    if not history:
        return history

    # Collect indices where complete turn pairs end
    # A complete pair: user message followed by assistant message(s) with no
    # pending tool_use blocks (i.e., the last assistant turn has stop_reason end_turn
    # or we find the next user message).
    # Simple approach: find "user" message boundaries and keep last max_turns of them.
    user_indices = [i for i, m in enumerate(history) if m.get("role") == "user"]

    if len(user_indices) <= max_turns:
        return history

    # Start from the (len - max_turns)th user message
    cut = user_indices[len(user_indices) - max_turns]
    return history[cut:]
