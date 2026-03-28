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
import inspect
import pkgutil
import sys
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
