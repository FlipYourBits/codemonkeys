# tests/test_runner.py
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.core.run_result import RunResult
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.events import EventEmitter, EventType


def _make_assistant_message(
    usage: dict[str, Any] | None = None,
    content: list | None = None,
) -> MagicMock:
    from claude_agent_sdk import AssistantMessage

    msg = MagicMock(spec=AssistantMessage)
    msg.usage = usage or {"input_tokens": 100, "output_tokens": 50}
    msg.content = content or []
    return msg


def _make_result_message(
    result: str = "",
    structured_output: Any = None,
    usage: dict[str, Any] | None = None,
    cost: float | None = None,
    duration_ms: int = 500,
) -> MagicMock:
    from claude_agent_sdk import ResultMessage

    msg = MagicMock(spec=ResultMessage)
    msg.result = result
    msg.structured_output = structured_output
    msg.usage = usage or {"input_tokens": 200, "output_tokens": 100}
    msg.total_cost_usd = cost
    msg.duration_ms = duration_ms
    msg.num_turns = 1
    msg.model_usage = None
    return msg


def _make_agent() -> MagicMock:
    from claude_agent_sdk import AgentDefinition

    agent = MagicMock(spec=AgentDefinition)
    agent.prompt = "You are a test agent."
    agent.model = "sonnet"
    agent.tools = ["Read", "Bash"]
    agent.disallowedTools = []
    agent.permissionMode = "dontAsk"
    agent.description = "Test agent"
    return agent


class TestAgentRunnerReturnsRunResult:
    @pytest.mark.asyncio
    async def test_returns_run_result(self) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(
            result="done",
            structured_output={"key": "value"},
            cost=0.05,
            duration_ms=1234,
        )

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test")
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert isinstance(result, RunResult)
        assert result.structured == {"key": "value"}
        assert result.cost == 0.05
        assert result.duration_ms == 1234

    @pytest.mark.asyncio
    async def test_structured_output_parses_json_string(self) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(
            structured_output='{"parsed": true}',
        )

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test")
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert result.structured == {"parsed": True}


class TestAgentRunnerEmitsEvents:
    @pytest.mark.asyncio
    async def test_emits_agent_started_and_completed(self) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(result="done")

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        emitter = EventEmitter()
        events: list[tuple[EventType, Any]] = []
        emitter.on_any(lambda et, p: events.append((et, p)))

        runner = AgentRunner(cwd="/tmp/test", emitter=emitter)
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            await runner.run_agent(_make_agent(), "do stuff", log_name="test_agent")

        event_types = [e[0] for e in events]
        assert EventType.AGENT_STARTED in event_types
        assert EventType.AGENT_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_no_emitter_does_not_crash(self) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(result="done")

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test")
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert isinstance(result, RunResult)


class TestAgentRunnerLogging:
    @pytest.mark.asyncio
    async def test_writes_log_files(self, tmp_path: Path) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(result="done", structured_output={"out": 1})

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test", log_dir=tmp_path)
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            await runner.run_agent(_make_agent(), "do stuff", log_name="test_log")

        log_files = list(tmp_path.glob("test_log*.log"))
        md_files = list(tmp_path.glob("test_log*.md"))
        assert len(log_files) == 1
        assert len(md_files) == 1

        log_content = log_files[0].read_text()
        assert "agent_start" in log_content

        md_content = md_files[0].read_text()
        assert "System Prompt" in md_content
        assert "User Prompt" in md_content

    @pytest.mark.asyncio
    async def test_no_log_dir_skips_logging(self) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(result="done")

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test")
        with (
            patch("codemonkeys.core.runner.query", fake_query),
            patch("codemonkeys.core.runner.restrict"),
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert isinstance(result, RunResult)
