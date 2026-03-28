import logging
import sys
from pathlib import Path

import yaml
import anthropic

from config import ROUTER_MODEL, SKILLS_DIR

logger = logging.getLogger(__name__)

_ROUTER_SYSTEM = (
    "You are a request router. Given a user message and a list of skill domains, "
    "output ONLY the single best matching skill name exactly as written, or \"none\". "
    "No explanation, no punctuation, just the name."
)


def _skills_dir() -> Path:
    return Path(__file__).parent / SKILLS_DIR


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a SKILL.md file. Returns {} if none present."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def discover_skills() -> dict[str, str]:
    """Return {domain_name: description} for all skill domains."""
    result = {}
    for skill_md in sorted(_skills_dir().rglob("SKILL.md")):
        domain = skill_md.parent.name
        text = skill_md.read_text()
        fm = _parse_frontmatter(text)
        result[domain] = fm.get("description") or domain
    return result


def select_skill(user_message: str) -> str | None:
    """Route a user message to a skill domain. Returns domain name or None."""
    skills = discover_skills()
    if not skills:
        return None

    skill_list = "\n".join(f"- {name}: {desc}" for name, desc in skills.items())
    prompt = f"Skills:\n{skill_list}\n\nUser message: {user_message}"

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=32,
            system=_ROUTER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        result = resp.content[0].text.strip().lower()
        if result == "none" or result not in skills:
            return None
        return result
    except Exception as e:
        logger.warning("Skill routing failed: %s", e)
        return None


def load_skill_instructions(skill_name: str) -> str | None:
    """Return full SKILL.md content for the given domain, or None."""
    path = _skills_dir() / skill_name / "SKILL.md"
    if path.exists():
        return path.read_text()
    return None
