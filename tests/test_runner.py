from unittest.mock import patch

import pytest
from pydantic import BaseModel

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock

from codemonkeys.core.events import (
    Event,
)
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import AgentDefinition


class ReviewOutput(BaseModel):
    findings: list[str]


def _make_agent(**overrides) -> AgentDefinition:
    defaults = {
        "name": "test-agent",
        "model": "sonnet",
        "system_prompt": "You are a test agent.",
        "tools": ["Read", "Grep"],
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def _make_assistant_message(content=None, usage=None):
    return AssistantMessage(
        content=content or [],
        model="sonnet",
        usage=usage or {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )


def _make_tool_use_block(name="Read", input=None):
    return ToolUseBlock(id="tool-1", name=name, input=input or {})


def _make_result_message(
    text="", structured_output=None, cost=0.01, duration_ms=500, is_error=False
):
    return ResultMessage(
        subtype="result",
        duration_ms=duration_ms,
        duration_api_ms=duration_ms,
        is_error=is_error,
        num_turns=1,
        session_id="test-session",
        total_cost_usd=cost,
        usage={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
        result=text,
        structured_output=structured_output,
        stop_reason="end_turn",
    )


async def _fake_query_simple(**kwargs):
    yield _make_assistant_message(
        content=[_make_tool_use_block(name="Read", input={"file_path": "/foo.py"})],
        usage={"input_tokens": 500, "output_tokens": 100, "total_tokens": 600},
    )
    yield _make_result_message(text="All good")


async def _fake_query_structured(**kwargs):
    output = {"findings": ["unused import", "missing docstring"]}
    yield _make_result_message(
        text="",
        structured_output=output,
        cost=0.02,
        duration_ms=1200,
    )


@pytest.mark.asyncio
async def test_run_agent_basic():
    events: list[Event] = []

    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_simple):
        result = await run_agent(
            _make_agent(),
            "Review the code",
            on_event=events.append,
        )

    assert result.text == "All good"
    assert result.error is None
    assert result.cost_usd == 0.01

    event_types = [type(e).__name__ for e in events]
    assert "AgentStarted" in event_types
    assert "ToolCall" in event_types
    assert "AgentCompleted" in event_types


@pytest.mark.asyncio
async def test_run_agent_structured_output():
    events: list[Event] = []

    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_structured):
        result = await run_agent(
            _make_agent(output_schema=ReviewOutput),
            "Review the code",
            on_event=events.append,
        )

    assert result.output is not None
    assert isinstance(result.output, ReviewOutput)
    assert result.output.findings == ["unused import", "missing docstring"]
    assert result.cost_usd == 0.02


@pytest.mark.asyncio
async def test_run_agent_no_event_handler():
    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_simple):
        result = await run_agent(_make_agent(), "Review the code")

    assert result.text == "All good"


@pytest.mark.asyncio
async def test_run_agent_error_handling():
    async def _fake_query_error(**kwargs):
        yield _make_result_message(text="Something went wrong", is_error=True)

    events: list[Event] = []
    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_error):
        result = await run_agent(
            _make_agent(),
            "Do something",
            on_event=events.append,
        )

    assert result.error is not None
    event_types = [type(e).__name__ for e in events]
    assert "AgentError" in event_types
