"""Tests for the project memory agent factory."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def test_full_mode_returns_agent_definition() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent

    agent = make_project_memory_agent(mode="full")
    assert isinstance(agent, AgentDefinition)
    assert agent.model == "sonnet"
    assert agent.tools is not None
    assert "Write" in agent.tools
    assert agent.permissionMode == "dontAsk"
    assert "full scan" in agent.prompt.lower() or "git ls-files" in agent.prompt


def test_incremental_mode_includes_diff() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent

    diff = "diff --git a/foo.py b/foo.py\n+new line"
    agent = make_project_memory_agent(mode="incremental", diff_text=diff)
    assert isinstance(agent, AgentDefinition)
    assert diff in agent.prompt


def test_incremental_mode_requires_diff() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent
    import pytest

    with pytest.raises(ValueError, match="diff_text is required"):
        make_project_memory_agent(mode="incremental", diff_text=None)


def test_full_mode_does_not_include_diff_section() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent

    agent = make_project_memory_agent(mode="full")
    assert "## Diff" not in agent.prompt


def test_tools_include_write_and_bash() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent

    agent = make_project_memory_agent(mode="full")
    assert agent.tools is not None
    assert "Read" not in agent.tools
    assert "Write" in agent.tools
    assert any("Bash" in t for t in agent.tools)


def test_description_mentions_project_memory() -> None:
    from codemonkeys.agents.project_memory import make_project_memory_agent

    agent = make_project_memory_agent(mode="full")
    assert (
        "architecture" in agent.description.lower()
        or "memory" in agent.description.lower()
    )
