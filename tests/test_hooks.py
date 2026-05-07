import pytest

from codemonkeys.core.hooks import build_tool_hooks, check_tool_allowed


def test_check_tool_allowed_simple_tools():
    allowed = ["Read", "Grep", "Bash(pytest*)"]
    assert check_tool_allowed("Read", {}, allowed) is True
    assert check_tool_allowed("Grep", {}, allowed) is True
    assert check_tool_allowed("Edit", {}, allowed) is False
    assert check_tool_allowed("Write", {}, allowed) is False


def test_check_tool_allowed_bash_patterns():
    allowed = ["Read", "Bash(pytest*)", "Bash(ruff*)"]
    assert check_tool_allowed("Bash", {"command": "pytest tests/ -v"}, allowed) is True
    assert check_tool_allowed("Bash", {"command": "ruff check ."}, allowed) is True
    assert check_tool_allowed("Bash", {"command": "rm -rf /"}, allowed) is False
    assert check_tool_allowed("Bash", {"command": ""}, allowed) is False


def test_check_tool_allowed_no_bash_patterns():
    allowed = ["Read", "Bash"]
    assert check_tool_allowed("Bash", {"command": "anything"}, allowed) is True


def test_check_tool_allowed_empty_list():
    assert check_tool_allowed("Read", {}, []) is False
    assert check_tool_allowed("Bash", {"command": "ls"}, []) is False


def test_build_tool_hooks_returns_none_when_no_bash_patterns():
    hooks = build_tool_hooks(["Read", "Grep"])
    assert hooks is None


def test_build_tool_hooks_returns_hook_for_bash_patterns():
    hooks = build_tool_hooks(["Read", "Bash(pytest*)"])
    assert hooks is not None
    assert "PreToolUse" in hooks
