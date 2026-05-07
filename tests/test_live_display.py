import time

from codemonkeys.core.events import (
    AgentCompleted,
    AgentStarted,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import RunResult, TokenUsage
from codemonkeys.display.live import LiveDisplay


def test_live_display_tracks_agent_state():
    display = LiveDisplay()
    display.handle(AgentStarted(agent_name="reviewer", timestamp=time.time(), model="sonnet"))
    assert "reviewer" in display.agents
    assert display.agents["reviewer"].model == "sonnet"


def test_live_display_updates_on_tool_call():
    display = LiveDisplay()
    display.handle(AgentStarted(agent_name="reviewer", timestamp=time.time(), model="sonnet"))
    display.handle(
        ToolCall(
            agent_name="reviewer",
            timestamp=time.time(),
            tool_name="Read",
            tool_input={"file_path": "/foo.py"},
        )
    )
    assert display.agents["reviewer"].current_tool == "Read"
    assert display.agents["reviewer"].tool_calls == 1


def test_live_display_updates_on_token_update():
    display = LiveDisplay()
    display.handle(AgentStarted(agent_name="reviewer", timestamp=time.time(), model="sonnet"))
    usage = TokenUsage(input_tokens=500, output_tokens=100)
    display.handle(
        TokenUpdate(agent_name="reviewer", timestamp=time.time(), usage=usage, cost_usd=0.005)
    )
    assert display.agents["reviewer"].usage.input_tokens == 500
    assert display.agents["reviewer"].cost_usd == 0.005


def test_live_display_marks_completed():
    display = LiveDisplay()
    display.handle(AgentStarted(agent_name="reviewer", timestamp=time.time(), model="sonnet"))
    usage = TokenUsage(input_tokens=1000, output_tokens=200)
    result = RunResult(output=None, text="done", usage=usage, cost_usd=0.01, duration_ms=500)
    display.handle(AgentCompleted(agent_name="reviewer", timestamp=time.time(), result=result))
    assert display.agents["reviewer"].completed is True


def test_live_display_tracks_denied_tools():
    display = LiveDisplay()
    display.handle(AgentStarted(agent_name="reviewer", timestamp=time.time(), model="sonnet"))
    display.handle(
        ToolDenied(
            agent_name="reviewer", timestamp=time.time(), tool_name="Bash", command="rm -rf /"
        )
    )
    assert display.agents["reviewer"].denied_calls == 1
