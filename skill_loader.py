import logging
import re
import sys
from pathlib import Path

import yaml
import anthropic

from config import ADDITIONAL_SKILL_CONTEXT, EXTERNAL_SKILL_DIRS, ROUTER_MODEL, SKILLS_DIR, _load_url

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


def _skill_name_from_url(dir_url: str) -> str:
    """Return the last non-empty path component of a URL as the skill domain name."""
    return dir_url.rstrip("/").rsplit("/", 1)[-1]


def discover_skills() -> dict[str, str]:
    """Return {domain_name: description} for all skill domains."""
    result = {}
    for skill_md in sorted(_skills_dir().rglob("SKILL.md")):
        domain = skill_md.parent.name
        text = skill_md.read_text()
        fm = _parse_frontmatter(text)
        result[domain] = fm.get("description") or domain

    for dir_url in EXTERNAL_SKILL_DIRS:
        domain = _skill_name_from_url(dir_url)
        skill_md_url = dir_url.rstrip("/") + "/SKILL.md"
        try:
            text = _load_url(skill_md_url)
            fm = _parse_frontmatter(text)
            result[domain] = fm.get("description") or domain
        except Exception as e:
            logger.warning("Failed to load SKILL.md for external skill %s: %s", domain, e)

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
        logger.info("LLM usage: model=%s input_tokens=%d output_tokens=%d", ROUTER_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        result = resp.content[0].text.strip().lower()
        if result == "none" or result not in skills:
            return None
        return result
    except Exception as e:
        logger.warning("Skill routing failed: %s", e)
        return None


def _additional_context_section(skill_name: str) -> str | None:
    """Return the additional context for a skill from ADDITIONAL_SKILL_CONTEXT, or None."""
    if not ADDITIONAL_SKILL_CONTEXT:
        return None
    pattern = rf"^## {re.escape(skill_name)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, ADDITIONAL_SKILL_CONTEXT, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip() or None
    return None


def load_skill_instructions(skill_name: str) -> str | None:
    """Return full SKILL.md content for the given domain, or None."""
    path = _skills_dir() / skill_name / "SKILL.md"
    if path.exists():
        instructions = path.read_text()
    else:
        # Fall back to external skill dirs
        instructions = None
        for dir_url in EXTERNAL_SKILL_DIRS:
            if _skill_name_from_url(dir_url) == skill_name:
                skill_md_url = dir_url.rstrip("/") + "/SKILL.md"
                try:
                    instructions = _load_url(skill_md_url)
                except Exception as e:
                    logger.warning("Failed to load instructions for external skill %s: %s", skill_name, e)
                break
        if instructions is None:
            return None

    extra = _additional_context_section(skill_name)
    if extra:
        instructions += f"\n\n## Personal context\n{extra}"
    return instructions
