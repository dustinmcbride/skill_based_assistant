import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ROUTER_MODEL = "claude-haiku-4-5-20251001"
AGENT_MODEL = "claude-opus-4-6"
MAX_TOKENS = 4096
ASSISTANT_DIR = Path(os.environ.get("ASSISTANT_DIR", "~/.assistant")).expanduser()
SKILLS_DIR = "skills"

SYSTEM_PROMPT = """
You are a personal assistant. You have access to local skills and remote MCP servers.
Use tools proactively. Prefer concise responses unless the user asks for detail.
""".strip()

MODE_PROMPTS = {
    "command": """
You are operating in COMMAND mode. The user sent a dictated or voice command and cannot receive
follow-up questions. Interpret the request, state any assumptions, execute immediately, and confirm
what you did. Never ask a clarifying question. If a request is unexecutable due to genuinely
missing required data, explain clearly what is missing — do not silently do nothing.
""".strip(),

    "chat": """
You are operating in CHAT mode. This is an interactive conversation. You may ask clarifying
questions when intent is ambiguous. Maintain a natural, conversational tone.
""".strip(),
}


def _load_url(url: str) -> str:
    """Load content from a file:// (or files://) URL or a GitHub raw path."""
    if url.startswith("file"):
        # Handle file:// and files:// (typo variant)
        local_path = url.split("://", 1)[1]
        return Path(local_path).read_text()
    else:
        # Treat as a GitHub raw path: owner/repo/refs/heads/branch/path
        github_pat = os.getenv("GITHUB_PAT", "")
        raw_url = f"https://raw.githubusercontent.com/{url}"
        headers = {"Authorization": f"token {github_pat}"} if github_pat else {}
        response = httpx.get(raw_url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text


def _load_config() -> dict:
    config_file_url = os.getenv("CONFIG_FILE_URL")
    if not config_file_url:
        return {}
    try:
        config_text = _load_url(config_file_url)
        return json.loads(config_text)
    except Exception as e:
        logger.warning("Failed to load config: %s", e)
        return {}


_CONFIG: dict = _load_config()


def _load_soul() -> str:
    soul_url = _CONFIG.get("soul_base_url", "")
    if not soul_url:
        return ""
    try:
        return _load_url(soul_url)
    except Exception as e:
        logger.warning("Failed to load soul: %s", e)
        return ""


def _load_personas() -> dict[str, str]:
    personas: dict[str, str] = {}
    for user_entry in _CONFIG.get("users", []):
        user_id = user_entry.get("id")
        persona_url = user_entry.get("persona_url")
        if not user_id or not persona_url:
            continue
        try:
            personas[user_id] = _load_url(persona_url)
        except Exception as e:
            logger.warning("Failed to load persona for %s: %s", user_id, e)
    return personas


SOUL_CONTENT: str = _load_soul()
USER_PERSONAS: dict[str, str] = _load_personas()
