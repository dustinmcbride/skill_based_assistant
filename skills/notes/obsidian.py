import os
from datetime import datetime
from pathlib import Path

from skills import register

_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "~/Documents/Obsidian")).expanduser()


def _vault_path() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT", str(_VAULT))).expanduser()


@register
def create_note(title: str, content: str, tags: str = "") -> str:
    """
    Create a new Markdown note in the Obsidian vault.

    Args:
        title: Note title (used as filename)
        content: Note body (Markdown)
        tags: Comma-separated tags (optional)
    """
    try:
        vault = _vault_path()
        vault.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
        path = vault / f"{safe_title}.md"

        if path.exists():
            # Avoid overwrite — create a timestamped variant
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = vault / f"{safe_title}-{ts}.md"

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        frontmatter_tags = "\n".join(f"  - {t}" for t in tag_list)
        frontmatter = (
            f"---\ntitle: {title}\ndate: {datetime.now().strftime('%Y-%m-%d')}\n"
            + (f"tags:\n{frontmatter_tags}\n" if tag_list else "")
            + "---\n\n"
        )

        path.write_text(frontmatter + content)
        return f"Created note '{path.name}' at {path}"
    except Exception as e:
        return f"Error creating note: {e}"


@register
def read_note(filename: str) -> str:
    """Read a note from the Obsidian vault by filename (with or without .md extension)."""
    try:
        vault = _vault_path()
        if not filename.endswith(".md"):
            filename += ".md"
        path = vault / filename
        if not path.exists():
            # Try case-insensitive search
            matches = [f for f in vault.rglob("*.md") if f.name.lower() == filename.lower()]
            if matches:
                path = matches[0]
            else:
                return f"Note '{filename}' not found in vault."
        return path.read_text()
    except Exception as e:
        return f"Error reading note: {e}"


@register
def search_notes(query: str) -> str:
    """Search note titles and contents in the Obsidian vault for the given query."""
    try:
        vault = _vault_path()
        if not vault.exists():
            return f"Vault not found at {vault}."

        results = []
        query_lower = query.lower()
        for note_path in sorted(vault.rglob("*.md"))[:500]:
            try:
                text = note_path.read_text(errors="replace")
                if query_lower in text.lower() or query_lower in note_path.stem.lower():
                    # Find matching excerpt
                    idx = text.lower().find(query_lower)
                    if idx >= 0:
                        start = max(0, idx - 60)
                        end = min(len(text), idx + 120)
                        excerpt = text[start:end].replace("\n", " ").strip()
                    else:
                        excerpt = text[:120].replace("\n", " ").strip()
                    mtime = datetime.fromtimestamp(note_path.stat().st_mtime).strftime("%Y-%m-%d")
                    results.append(f"[{mtime}] {note_path.name}\n  ...{excerpt}...")
            except Exception:
                pass

        if not results:
            return f"No notes matching '{query}'."
        return f"Found {len(results)} note(s):\n\n" + "\n\n".join(results[:20])
    except Exception as e:
        return f"Error searching notes: {e}"


@register
def append_to_note(filename: str, content: str) -> str:
    """Append content to an existing note in the Obsidian vault."""
    try:
        vault = _vault_path()
        if not filename.endswith(".md"):
            filename += ".md"
        path = vault / filename
        if not path.exists():
            return f"Note '{filename}' not found. Use create_note to create it first."
        with path.open("a") as f:
            f.write("\n" + content)
        return f"Appended {len(content)} characters to {path.name}."
    except Exception as e:
        return f"Error appending to note: {e}"
