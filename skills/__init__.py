"""
Skill registry. Provides @register decorator, get_tools(), and dispatch().

Usage in a skill module:
    from skills import register

    @register
    def list_files(path: str) -> str:
        "List files at the given path."
        ...
"""

import importlib
import importlib.util
import inspect
import pkgutil
import sys
import tempfile
from pathlib import Path
from typing import get_type_hints

_REGISTRY: dict[str, dict] = {}
_loaded = False


def register(fn):
    """Decorator that registers a function as a tool."""
    if not fn.__doc__:
        raise ValueError(f"Skill {fn.__name__!r} must have a docstring.")
    schema = _infer_schema(fn)
    _REGISTRY[fn.__name__] = {
        "name": fn.__name__,
        "description": inspect.cleandoc(fn.__doc__),
        "input_schema": schema,
        "_fn": fn,
    }
    return fn


def get_tools() -> list[dict]:
    """Return Anthropic-compatible tool definitions."""
    _load_all()
    return [
        {k: v for k, v in tool.items() if k != "_fn"}
        for tool in _REGISTRY.values()
    ]


def dispatch(name: str, inputs: dict) -> str:
    """Execute a registered skill by name."""
    _load_all()
    if name not in _REGISTRY:
        raise ValueError(f"Unknown skill: {name!r}")
    fn = _REGISTRY[name]["_fn"]
    return fn(**inputs)


def _load_module_from_path(module_name: str, file_path: Path):
    import logging
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to import external skill module %s: %s", module_name, e
        )


def _load_all():
    global _loaded
    if _loaded:
        return
    _loaded = True

    skills_dir = Path(__file__).parent
    package_name = __name__  # "skills"

    # Add parent of skills/ to sys.path so imports work
    parent = str(skills_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    for finder, modname, ispkg in pkgutil.walk_packages(
        path=[str(skills_dir)],
        prefix=package_name + ".",
        onerror=lambda x: None,
    ):
        if not ispkg and modname != package_name:
            try:
                importlib.import_module(modname)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to import skill module %s: %s", modname, e
                )

    # Load external skill dirs
    try:
        from config import EXTERNAL_SKILL_DIRS, _load_url, list_dir_url
    except Exception:
        EXTERNAL_SKILL_DIRS = []

    import logging
    ext_logger = logging.getLogger(__name__)

    for dir_url in EXTERNAL_SKILL_DIRS:
        dir_name = dir_url.rstrip("/").rsplit("/", 1)[-1]
        try:
            files = list_dir_url(dir_url)
        except Exception as e:
            ext_logger.warning("Failed to list external skill dir %s: %s", dir_url, e)
            continue

        for file_info in files:
            name = file_info["name"]
            if not name.endswith(".py"):
                continue
            stem = Path(name).stem
            module_name = f"skills_ext.{dir_name}.{stem}"

            file_url = file_info["url"]
            if file_url.startswith("file"):
                local_path = Path(file_url.split("://", 1)[1])
                _load_module_from_path(module_name, local_path)
            else:
                # GitHub: download to temp file then load
                try:
                    content = _load_url(file_url)
                except Exception as e:
                    ext_logger.warning("Failed to fetch %s: %s", file_url, e)
                    continue
                try:
                    with tempfile.NamedTemporaryFile(
                        suffix=".py", delete=False, mode="w", encoding="utf-8"
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = Path(tmp.name)
                    _load_module_from_path(module_name, tmp_path)
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass


_TYPE_MAP = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array", "items": {"type": "string"}},
}


def _infer_schema(fn) -> dict:
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name == "return":
            continue
        hint = hints.get(param_name, str)
        # Unwrap Optional[X] -> X
        origin = getattr(hint, "__origin__", None)
        args = getattr(hint, "__args__", ())
        if origin is not None and type(None) in args:
            hint = next((a for a in args if a is not type(None)), str)

        prop = _TYPE_MAP.get(hint, {"type": "string"})
        properties[param_name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
