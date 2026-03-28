import logging
import re
from dataclasses import dataclass
from pathlib import Path

from config import ASSISTANT_DIR, _CONFIG

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-z0-9-]+$")

# Index of users discovered from CONFIG_FILE_URL
_KNOWN_USERS: dict[str, dict] = {
    entry["id"]: entry
    for entry in _CONFIG.get("users", [])
    if "id" in entry
}


@dataclass
class User:
    username: str
    display_name: str
    history_path: Path


def load_user(username: str) -> User:
    if not USERNAME_RE.match(username):
        raise ValueError(
            f"Invalid username {username!r}. Must match ^[a-z0-9-]+$"
        )

    if username not in _KNOWN_USERS:
        raise ValueError(
            f"Unknown user {username!r}. Known users: {list(_KNOWN_USERS)}"
        )

    config_entry = _KNOWN_USERS[username]
    base = ASSISTANT_DIR / "users" / username
    base.mkdir(parents=True, exist_ok=True)

    return User(
        username=username,
        display_name=config_entry.get("name") or username.capitalize(),
        history_path=base / "history.json",
    )
