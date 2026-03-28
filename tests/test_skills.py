"""Tests for skill registration and dispatch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import skills


def setup_function():
    # Reset registry and _loaded flag so each test starts fresh
    skills._REGISTRY.clear()
    skills._loaded = False


def test_register_and_get_tools():
    @skills.register
    def my_tool(name: str, count: int = 1) -> str:
        "A test tool."
        return f"{name} x{count}"

    tools = skills.get_tools()
    names = [t["name"] for t in tools]
    assert "my_tool" in names

    tool = next(t for t in tools if t["name"] == "my_tool")
    assert tool["description"] == "A test tool."
    assert tool["input_schema"]["properties"]["name"]["type"] == "string"
    assert tool["input_schema"]["properties"]["count"]["type"] == "integer"
    assert "name" in tool["input_schema"]["required"]
    assert "count" not in tool["input_schema"]["required"]
    # _fn must not be exposed
    assert "_fn" not in tool


def test_dispatch():
    @skills.register
    def greet(name: str) -> str:
        "Greet someone."
        return f"Hello, {name}!"

    result = skills.dispatch("greet", {"name": "World"})
    assert result == "Hello, World!"


def test_dispatch_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown skill"):
        skills.dispatch("does_not_exist", {})


def test_register_requires_docstring():
    import pytest
    with pytest.raises(ValueError, match="must have a docstring"):
        @skills.register
        def no_doc(x: str) -> str:
            return x


def test_schema_excludes_fn_key():
    @skills.register
    def another_tool(path: str) -> str:
        "Another tool."
        return path

    for tool in skills.get_tools():
        assert "_fn" not in tool


def test_filesystem_skills_load():
    # Force a clean reload of skill modules so @register re-runs
    import importlib, sys
    skills._REGISTRY.clear()
    skills._loaded = False
    for mod in list(sys.modules):
        if mod.startswith("skills."):
            importlib.reload(sys.modules[mod])

    tools = skills.get_tools()
    names = [t["name"] for t in tools]
    for expected in ("read_file", "write_file", "list_directory", "find_files", "file_exists"):
        assert expected in names, f"Expected skill '{expected}' not found in {names}"


def test_dispatch_read_nonexistent(tmp_path, monkeypatch):
    import importlib, sys
    # Point ALLOWED_PATHS at tmp_path so the path check passes
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    skills._REGISTRY.clear()
    skills._loaded = False
    for mod in list(sys.modules):
        if mod.startswith("skills."):
            importlib.reload(sys.modules[mod])
    skills.get_tools()  # trigger load

    result = skills.dispatch("read_file", {"path": str(tmp_path / "nonexistent.txt")})
    assert "error" in result.lower() or "not found" in result.lower()
