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
def write_trip_file(filename: str, content: str) -> str:
    """
    Write a trip note to the Obsidian vault under Trips/.

    Args:
        filename: Bare filename, e.g. "2026-05-02_Sacramento.md" (no path prefix)
        content: Full Markdown content of the trip note
    """
    try:
        # Ensure filename has .md extension
        if not filename.endswith(".md"):
            filename += ".md"

        # Strip any accidental path prefix — only the basename is allowed
        filename = Path(filename).name

        trips_dir = _trips_dir()
        path = trips_dir / filename

        path.write_text(content)
        return f"Trip filed: Trips/{filename}"
    except Exception as e:
        return f"Error writing trip file: {e}"
