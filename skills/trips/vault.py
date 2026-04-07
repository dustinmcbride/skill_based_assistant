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

    Always overwrites the file with the provided content. When updating an
    existing trip, the caller is responsible for merging old and new information
    into a single well-formatted document before calling this function.

    Args:
        filename: Bare filename, e.g. "2026-05-02_Sacramento.md" (no path prefix)
        content: Complete markdown content for the trip note
    """
    try:
        # Ensure filename has .md extension
        if not filename.endswith(".md"):
            filename += ".md"

        # Strip any accidental path prefix — only the basename is allowed
        filename = Path(filename).name

        trips_dir = _trips_dir()
        path = trips_dir / filename
        existed = path.exists()

        path.write_text(content)
        action = "updated" if existed else "filed"
        return f"Trip {action}: Trips/{filename}"
    except Exception as e:
        return f"Error writing trip file: {e}"
