import os
from pathlib import Path

from skills import register

_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "~/Documents/Obsidian")).expanduser()


def _trips_dir() -> Path:
    vault = Path(os.environ.get("OBSIDIAN_VAULT", str(_VAULT))).expanduser()
    trips = vault / "Trips"
    trips.mkdir(parents=True, exist_ok=True)
    return trips


@register
def read_trip_file(filename: str) -> str:
    """
    Read an existing trip note from the Obsidian vault under Trips/.

    Args:
        filename: Bare filename, e.g. "2026-05-02_Sacramento.md" (no path prefix)

    Returns the file content, or an empty string if the file does not exist.
    """
    try:
        if not filename.endswith(".md"):
            filename += ".md"
        filename = Path(filename).name
        path = _trips_dir() / filename
        if not path.exists():
            return ""
        return path.read_text()
    except Exception as e:
        return f"Error reading trip file: {e}"


@register
def write_trip_file(filename: str, content: str) -> str:
    """
    Write a trip note to the Obsidian vault under Trips/.

    If the file already exists, the new content is appended rather than
    overwriting, so details from multiple emails (flights, hotels, etc.)
    are preserved in a single note.

    Args:
        filename: Bare filename, e.g. "2026-05-02_Sacramento.md" (no path prefix)
        content: Markdown content to add to the trip note
    """
    try:
        # Ensure filename has .md extension
        if not filename.endswith(".md"):
            filename += ".md"

        # Strip any accidental path prefix — only the basename is allowed
        filename = Path(filename).name

        trips_dir = _trips_dir()
        path = trips_dir / filename

        if path.exists():
            existing = path.read_text()
            combined = existing.rstrip("\n") + "\n\n---\n\n" + content
            path.write_text(combined)
            return f"Trip updated (appended): Trips/{filename}"
        else:
            path.write_text(content)
            return f"Trip filed: Trips/{filename}"
    except Exception as e:
        return f"Error writing trip file: {e}"
