import time

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    EventHandler,
    ToolCall,
    ToolDenied,
    ToolResult,
    TokenUpdate,
)
from codemonkeys.core.types import RunResult, TokenUsage


def test_event_base_fields():
    e = AgentStarted(agent_name="reviewer", timestamp=1000.0, model="sonnet")
    assert e.agent_name == "reviewer"
    assert e.timestamp == 1000.0
    assert e.model == "sonnet"


def test_tool_call_event():
    e = ToolCall(
        agent_name="reviewer",
        timestamp=time.time(),
        tool_name="Read",
        tool_input={"file_path": "/foo.py"},
    )
    assert e.tool_name == "Read"
    assert e.tool_input["file_path"] == "/foo.py"


def test_tool_denied_event():
    e = ToolDenied(
        agent_name="reviewer",
        timestamp=time.time(),
        tool_name="Bash",
        command="rm -rf /",
    )
    assert e.tool_name == "Bash"
    assert e.command == "rm -rf /"


def test_token_update_event():
    usage = TokenUsage(input_tokens=500, output_tokens=100)
    e = TokenUpdate(
        agent_name="reviewer",
        timestamp=time.time(),
        usage=usage,
        cost_usd=0.005,
    )
    assert e.usage.input_tokens == 500
    assert e.cost_usd == 0.005


def test_agent_completed_event():
    usage = TokenUsage(input_tokens=1000, output_tokens=200)
    result = RunResult(
        output=None, text="done", usage=usage, cost_usd=0.01, duration_ms=500
    )
    e = AgentCompleted(
        agent_name="reviewer",
        timestamp=time.time(),
        result=result,
    )
    assert e.result.text == "done"


def test_agent_error_event():
    e = AgentError(
        agent_name="reviewer",
        timestamp=time.time(),
        error="Rate limit exceeded",
    )
    assert e.error == "Rate limit exceeded"


def test_event_handler_type():
    """EventHandler is just a callable that takes an Event."""
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    h: EventHandler = handler
    h(AgentStarted(agent_name="x", timestamp=0.0, model="sonnet"))
    assert len(received) == 1
