import os
from pathlib import Path

from skills import register

_DEFAULT_ALLOWED = os.environ.get(
    "ALLOWED_PATHS",
    os.environ.get("OBSIDIAN_VAULT", "~/Documents/Obsidian"),
)
_ALLOWED: list[Path] = [
    Path(p.strip()).expanduser().resolve()
    for p in _DEFAULT_ALLOWED.split(",")
    if p.strip()
]


def _expand(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if _ALLOWED and not any(p == a or a in p.parents for a in _ALLOWED):
        allowed_str = ", ".join(str(a) for a in _ALLOWED)
        raise PermissionError(f"Access denied: {p} is outside allowed paths ({allowed_str})")
    return p


@register
def read_file(path: str) -> str:
    """Read the contents of a file. Returns the first 200 lines for large files."""
    try:
        p = _expand(path)
        lines = p.read_text(errors="replace").splitlines()
        if len(lines) > 200:
            truncated = len(lines) - 200
            return "\n".join(lines[:200]) + f"\n... ({truncated} more lines truncated)"
        return "\n".join(lines)
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except Exception as e:
        return f"Error reading {path}: {e}"


@register
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    try:
        p = _expand(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} characters to {p}"
    except Exception as e:
        return f"Error writing {path}: {e}"


@register
def append_file(path: str, content: str) -> str:
    """Append content to a file. Creates the file if it does not exist."""
    try:
        p = _expand(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(content)
        return f"Appended {len(content)} characters to {p}"
    except Exception as e:
        return f"Error appending to {path}: {e}"


@register
def list_directory(path: str) -> str:
    """List files and directories at the given path with sizes and modification times."""
    try:
        p = _expand(path)
        if not p.is_dir():
            return f"Error: not a directory: {path}"
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = []
        for entry in entries:
            try:
                stat = entry.stat()
                kind = "DIR " if entry.is_dir() else "FILE"
                size = f"{stat.st_size:>10} bytes" if entry.is_file() else " " * 16
                import datetime
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                lines.append(f"{kind}  {size}  {mtime}  {entry.name}")
            except Exception:
                lines.append(f"????  {entry.name}")
        if not lines:
            return f"{p} is empty."
        return f"{p}:\n" + "\n".join(lines)
    except FileNotFoundError:
        return f"Error: directory not found: {path}"
    except Exception as e:
        return f"Error listing {path}: {e}"


@register
def find_files(directory: str, pattern: str) -> str:
    """Find files matching a glob pattern under the given directory."""
    try:
        p = _expand(directory)
        matches = sorted(p.rglob(pattern))
        if not matches:
            return f"No files matching '{pattern}' found under {p}"
        return "\n".join(str(m) for m in matches[:100])
    except Exception as e:
        return f"Error searching {directory}: {e}"


@register
def file_exists(path: str) -> str:
    """Check whether a file or directory exists at the given path."""
    p = _expand(path)
    if p.exists():
        kind = "directory" if p.is_dir() else "file"
        return f"Yes — {kind} exists at {p}"
    return f"No — nothing exists at {p}"
