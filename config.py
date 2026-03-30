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


def _load_additional_skill_context() -> str:
    url = _CONFIG.get("additional_skill_context_url", "")
    if not url:
        return ""
    try:
        return _load_url(url)
    except Exception as e:
        logger.warning("Failed to load additional skill context: %s", e)
        return ""


def list_dir_url(dir_url: str) -> list[dict]:
    """List files in a directory URL. Returns list of {name, url} dicts.

    For file:// URLs, lists files in the local directory.
    For GitHub paths (owner/repo/refs/heads/branch/path), uses the GitHub Contents API.
    Each returned dict has 'name' (filename) and 'url' (loadable URL for that file).
    """
    if dir_url.startswith("file"):
        local_path = Path(dir_url.split("://", 1)[1])
        return [
            {"name": f.name, "url": f"file://{f}"}
            for f in sorted(local_path.iterdir())
            if f.is_file()
        ]
    else:
        # GitHub path: owner/repo/refs/heads/branch/sub/path
        # Parse into owner, repo, ref, and subpath
        parts = dir_url.split("/")
        # parts[0]=owner, parts[1]=repo, parts[2]="refs", parts[3]="heads", parts[4]=branch
        owner = parts[0]
        repo = parts[1]
        branch = parts[4]
        subpath = "/".join(parts[5:]) if len(parts) > 5 else ""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{subpath}?ref={branch}"
        github_pat = os.getenv("GITHUB_PAT", "")
        headers = {"Authorization": f"token {github_pat}"} if github_pat else {}
        response = httpx.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        entries = response.json()
        result = []
        for entry in entries:
            if entry.get("type") == "file":
                # Build a GitHub raw path compatible with _load_url
                file_raw_path = f"{owner}/{repo}/refs/heads/{branch}/{subpath}/{entry['name']}".replace("//", "/")
                result.append({"name": entry["name"], "url": file_raw_path})
        return result


def _load_external_skill_dirs() -> list[str]:
    return _CONFIG.get("external_skill_dirs", [])


def get_user_skill_config(user_id: str, skill_name: str) -> dict:
    """Return the skill-specific config dict for a user, or {} if not set.

    Reads from config.json: users[i].skills.<skill_name>
    """
    for user_entry in _CONFIG.get("users", []):
        if user_entry.get("id") == user_id:
            return (user_entry.get("skills") or {}).get(skill_name, {})
    return {}


SOUL_CONTENT: str = _load_soul()
USER_PERSONAS: dict[str, str] = _load_personas()
ADDITIONAL_SKILL_CONTEXT: str = _load_additional_skill_context()
EXTERNAL_SKILL_DIRS: list[str] = _load_external_skill_dirs()
