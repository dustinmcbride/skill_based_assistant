import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

from config import AGENT_MODEL, ASSISTANT_DIR, ROUTER_MODEL, _CONFIG, _load_url

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_PERSONA = (
    "You are speaking with a user who has not set up a profile. "
    "Be friendly, professional, and helpful."
)

_PERSONA_CACHE: dict[str, str] = {}

_KNOWN_USERS: dict[str, dict] = {
    entry["id"]: entry
    for entry in _CONFIG.get("users", [])
    if "id" in entry
}


@dataclass
class UserContext:
    user_id: str          # "dustin" or "anon-slack-U09XYZ"
    display_name: str     # "Tim Fish" or "Unknown User"
    persona: str          # Loaded persona markdown or DEFAULT_PERSONA
    active_channel: str   # "telegram" | "slack" | "cli" | "email"
    channels: dict        # {"telegram": "6211085845", "slack": "U09JULETA74"}
    history_path: Path    # memory/users/<user_id>/<channel>/history.json
    cross_channel_summary: str  # Injected into system prompt; "" if none
    is_anonymous: bool    # True if no config entry matched


def _load_persona(persona_url: str | None) -> str:
    """Load persona markdown from a URL. Returns DEFAULT_PERSONA on failure or missing URL."""
    if not persona_url:
        return DEFAULT_PERSONA
    if persona_url in _PERSONA_CACHE:
        return _PERSONA_CACHE[persona_url]
    try:
        content = _load_url(persona_url)
        _PERSONA_CACHE[persona_url] = content
        return content
    except Exception as e:
        logger.warning("Failed to load persona from %s: %s", persona_url, e)
        return DEFAULT_PERSONA


def build_cross_channel_summary(ctx: "UserContext") -> str:
    """
    Build a brief cross-channel activity summary for injection into the system prompt.

    Reads the last 5 user turns from each channel directory that is NOT the active
    channel. Returns "" if no other channel history exists or on any error.

    Note: history files do not store timestamps, so the 30-day lookback is
    approximated by the last 5 user turns only.
    """
    user_dir = ASSISTANT_DIR / "users" / ctx.user_id
    if not user_dir.exists():
        return ""

    channel_snippets: list[tuple[str, list[str]]] = []
    for channel_dir in sorted(user_dir.iterdir()):
        if not channel_dir.is_dir() or channel_dir.name == ctx.active_channel:
            continue
        history_file = channel_dir / "history.json"
        if not history_file.exists():
            continue
        try:
            history = json.loads(history_file.read_text())
        except Exception:
            continue

        # Last 5 user turns (excluding tool result turns)
        user_turns = [
            m for m in history
            if m.get("role") == "user"
            and not (
                isinstance(m.get("content"), list)
                and any(
                    b.get("type") == "tool_result"
                    for b in m["content"]
                    if isinstance(b, dict)
                )
            )
        ][-5:]

        texts: list[str] = []
        for turn in user_turns:
            content = turn["content"]
            if isinstance(content, str):
                texts.append(content[:200])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block["text"][:200])
                        break

        if texts:
            channel_snippets.append((channel_dir.name, texts))

    if not channel_snippets:
        return ""

    raw_lines: list[str] = []
    for channel_name, texts in channel_snippets:
        raw_lines.append(f"Channel: {channel_name}")
        for t in texts:
            raw_lines.append(f"  - {t}")

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=200,
            system=(
                "Summarize the following recent user activity across channels. "
                "Output bullet points in the format '- ChannelName: brief summary'. "
                "Cap at 100 words total. Be very concise."
            ),
            messages=[{"role": "user", "content": "\n".join(raw_lines)}],
        )
        return "## Recent activity across channels\n" + response.content[0].text
    except Exception as e:
        logger.warning("Failed to generate cross-channel summary: %s", e)
        return ""


def _build_context(entry: dict, channel: str) -> "UserContext":
    user_id = entry["id"]
    channels = entry.get("channels", {})
    persona = _load_persona(entry.get("persona_url"))
    history_path = ASSISTANT_DIR / "users" / user_id / channel / "history.json"
    ctx = UserContext(
        user_id=user_id,
        display_name=entry.get("name") or user_id.capitalize(),
        persona=persona,
        active_channel=channel,
        channels=channels,
        history_path=history_path,
        cross_channel_summary="",
        is_anonymous=False,
    )
    ctx.cross_channel_summary = build_cross_channel_summary(ctx)
    return ctx


def load_user_context(channel: str, channel_id: str) -> "UserContext":
    """
    Look up a user by channel + channel_id.
    Returns an anonymous UserContext if no matching user is found in config.
    Used by webhook handlers (Telegram, Slack).
    """
    for entry in _CONFIG.get("users", []):
        channels = entry.get("channels", {})
        if str(channels.get(channel, "")) == str(channel_id):
            return _build_context(entry, channel)

    # No match — anonymous user
    user_id = f"anon-{channel}-{channel_id}"
    return UserContext(
        user_id=user_id,
        display_name="Unknown User",
        persona=DEFAULT_PERSONA,
        active_channel=channel,
        channels={channel: channel_id},
        history_path=ASSISTANT_DIR / "users" / user_id / channel / "history.json",
        cross_channel_summary="",
        is_anonymous=True,
    )


def load_user_context_by_id(user_id: str, channel: str = "cli") -> "UserContext":
    """
    Look up a user by user_id and channel.
    Raises ValueError if the user is not in config or has an invalid format.
    Used by run.py (CLI) where the username is always known.
    """
    if not USERNAME_RE.match(user_id):
        raise ValueError(
            f"Invalid user_id {user_id!r}. Must match ^[a-z0-9-]+$"
        )
    if user_id not in _KNOWN_USERS:
        raise ValueError(
            f"Unknown user {user_id!r}. Known users: {list(_KNOWN_USERS)}"
        )
    return _build_context(_KNOWN_USERS[user_id], channel)
