"""Integration test — demonstrates parallel agent composition."""

import asyncio
from unittest.mock import patch

import pytest

from codemonkeys.agents.python_file_reviewer import (
    FileFindings,
    make_python_file_reviewer,
)
from codemonkeys.core.events import AgentCompleted, AgentStarted, Event
from codemonkeys.core.runner import run_agent
from codemonkeys.display.live import LiveDisplay

from claude_agent_sdk import ResultMessage


def _make_result_message(structured_output):
    """Create a real ResultMessage for testing."""
    return ResultMessage(
        subtype="result",
        duration_ms=800,
        duration_api_ms=800,
        is_error=False,
        num_turns=1,
        session_id="test",
        total_cost_usd=0.015,
        usage={"input_tokens": 2000, "output_tokens": 500, "total_tokens": 2500},
        result="",
        structured_output=structured_output,
        stop_reason="end_turn",
    )


def _make_fake_query(findings: list[dict]):
    async def _fake(**kwargs):
        yield _make_result_message({"results": findings})

    return _fake


@pytest.mark.asyncio
async def test_parallel_agents_with_display():
    """Run multiple agents in parallel, collect results, verify composition."""
    agents = [
        make_python_file_reviewer(["src/a.py"], model="haiku"),
        make_python_file_reviewer(["src/b.py"], model="haiku"),
    ]

    findings_a = [
        {
            "file": "src/a.py",
            "line": 10,
            "severity": "medium",
            "category": "quality",
            "title": "unused import",
            "description": "os is imported but not used",
            "suggestion": "remove it",
        }
    ]
    findings_b: list[dict] = []

    events: list[Event] = []
    display = LiveDisplay()

    def fan_out(event: Event) -> None:
        events.append(event)
        display.handle(event)

    fake_queries = [_make_fake_query(findings_a), _make_fake_query(findings_b)]
    call_count = 0

    async def _dispatch_fake(**kwargs):
        nonlocal call_count
        idx = call_count
        call_count += 1
        async for msg in fake_queries[idx](**kwargs):
            yield msg

    with patch("codemonkeys.core.runner.query", side_effect=_dispatch_fake):
        results = await asyncio.gather(
            *[run_agent(a, "Review", on_event=fan_out) for a in agents]
        )

    # Both returned structured output
    assert all(r.output is not None for r in results)
    assert isinstance(results[0].output, FileFindings)
    assert len(results[0].output.results) == 1
    assert len(results[1].output.results) == 0

    # Events were emitted for both
    started = [e for e in events if isinstance(e, AgentStarted)]
    completed = [e for e in events if isinstance(e, AgentCompleted)]
    assert len(started) == 2
    assert len(completed) == 2

    # Display tracked both agents
    assert len(display.agents) == 2
