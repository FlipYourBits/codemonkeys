import io

from rich.console import Console

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    RateLimitHit,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import RunResult, TokenUsage
from codemonkeys.display.stdout import make_stdout_printer


def _capture_printer():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=200)
    printer = make_stdout_printer(console=console)
    return printer, buf


def test_stdout_printer_agent_started():
    printer, buf = _capture_printer()
    printer(AgentStarted(agent_name="reviewer", timestamp=0.0, model="sonnet"))
    output = buf.getvalue()
    assert "reviewer" in output
    assert "sonnet" in output


def test_stdout_printer_tool_call():
    printer, buf = _capture_printer()
    printer(
        ToolCall(
            agent_name="r",
            timestamp=0.0,
            tool_name="Read",
            tool_input={"file_path": "app.py"},
        )
    )
    output = buf.getvalue()
    assert "Read" in output
    assert "app.py" in output


def test_stdout_printer_tool_denied():
    printer, buf = _capture_printer()
    printer(
        ToolDenied(
            agent_name="r", timestamp=0.0, tool_name="Bash", command="rm -rf /"
        )
    )
    output = buf.getvalue()
    assert "DENIED" in output


def test_stdout_printer_token_update():
    printer, buf = _capture_printer()
    printer(
        TokenUpdate(
            agent_name="r",
            timestamp=0.0,
            usage=TokenUsage(
                input_tokens=1000,
                output_tokens=200,
                cache_read_tokens=50,
                cache_creation_tokens=10,
            ),
            cost_usd=0.005,
        )
    )
    output = buf.getvalue()
    assert "0.005" in output.replace(" ", "")


def test_stdout_printer_agent_completed():
    printer, buf = _capture_printer()
    result = RunResult(
        output=None,
        text="done",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        cost_usd=0.01,
        duration_ms=5000,
    )
    printer(
        AgentCompleted(agent_name="reviewer", timestamp=0.0, result=result)
    )
    output = buf.getvalue()
    assert "done" in output.lower() or "reviewer" in output


def test_stdout_printer_agent_error():
    printer, buf = _capture_printer()
    printer(
        AgentError(agent_name="reviewer", timestamp=0.0, error="kaboom")
    )
    output = buf.getvalue()
    assert "kaboom" in output


def test_stdout_printer_rate_limit_rejected():
    printer, buf = _capture_printer()
    printer(
        RateLimitHit(
            agent_name="r",
            timestamp=0.0,
            rate_limit_type="tokens",
            status="rejected",
            wait_seconds=30,
        )
    )
    output = buf.getvalue()
    assert "rate limited" in output.lower()


def test_stdout_printer_rate_limit_non_rejected_silent():
    printer, buf = _capture_printer()
    printer(
        RateLimitHit(
            agent_name="r",
            timestamp=0.0,
            rate_limit_type="tokens",
            status="ok",
            wait_seconds=0,
        )
    )
    output = buf.getvalue()
    assert "rate limited" not in output.lower()
