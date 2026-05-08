"""Tests for codemonkeys.display.formatting."""

from __future__ import annotations


from codemonkeys.core.events import (
    RawMessage,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import TokenUsage
from codemonkeys.display.formatting import (
    format_event_trace,
    format_tool_call,
    format_tool_result,
    severity_style,
    system_message_label,
)


# ---------------------------------------------------------------------------
# format_tool_call
# ---------------------------------------------------------------------------


def test_format_tool_call_read():
    result = format_tool_call("Read", {"file_path": "/src/app.py"})
    assert result == "Read(/src/app.py)"


def test_format_tool_call_edit():
    result = format_tool_call("Edit", {"file_path": "/src/app.py"})
    assert result == "Edit(/src/app.py)"


def test_format_tool_call_write():
    result = format_tool_call("Write", {"file_path": "/src/app.py"})
    assert result == "Write(/src/app.py)"


def test_format_tool_call_grep():
    result = format_tool_call("Grep", {"pattern": "TODO", "path": "src/"})
    assert result == "Grep('TODO', path=src/)"


def test_format_tool_call_grep_no_path():
    result = format_tool_call("Grep", {"pattern": "TODO"})
    assert result == "Grep('TODO')"


def test_format_tool_call_bash():
    result = format_tool_call("Bash", {"command": "ruff check ."})
    assert result == "Bash($ ruff check .)"


def test_format_tool_call_bash_truncates():
    long_cmd = "x" * 200
    result = format_tool_call("Bash", {"command": long_cmd})
    assert len(result) < 210
    assert result.startswith("Bash($ ")


def test_format_tool_call_unknown():
    result = format_tool_call("CustomTool", {"key": "val"})
    assert "CustomTool" in result


def test_format_tool_call_missing_input():
    result = format_tool_call("Read", {})
    assert result == "Read(?)"


# ---------------------------------------------------------------------------
# format_tool_result
# ---------------------------------------------------------------------------


def test_format_tool_result_string():
    result = format_tool_result({"tool_use_result": "hello world"})
    assert result == "hello world"


def test_format_tool_result_long_string():
    long = "x" * 1000
    result = format_tool_result({"tool_use_result": long})
    assert "total chars" in result
    assert len(result) < 600


def test_format_tool_result_file():
    data = {
        "tool_use_result": {
            "file": {"filePath": "src/app.py", "numLines": 42, "content": "code here"}
        }
    }
    result = format_tool_result(data)
    assert "src/app.py" in result
    assert "42 lines" in result


def test_format_tool_result_file_short_summary():
    content = "x" * 2000
    data = {
        "tool_use_result": {
            "file": {"filePath": "big.py", "numLines": 100, "content": content}
        }
    }
    result = format_tool_result(data)
    assert result == "big.py (100 lines, 2000 chars)"


def test_format_tool_result_file_verbose_truncates():
    content = "x" * 2000
    data = {
        "tool_use_result": {
            "file": {"filePath": "big.py", "numLines": 100, "content": content}
        }
    }
    result = format_tool_result(data, verbose=True)
    assert "truncated" in result.lower()
    assert "big.py" in result


def test_format_tool_result_counts():
    data = {"tool_use_result": {"numFiles": 5, "numLines": 200}}
    result = format_tool_result(data)
    assert "5 files" in result
    assert "200 lines" in result


def test_format_tool_result_empty():
    result = format_tool_result({})
    assert result == ""


def test_format_tool_result_non_dict():
    result = format_tool_result({"tool_use_result": 42})
    assert result == ""


# ---------------------------------------------------------------------------
# format_event_trace
# ---------------------------------------------------------------------------


def test_format_event_trace_empty():
    assert format_event_trace([]) == "(empty trace)"


def test_format_event_trace_tool_call():
    events = [
        ToolCall(
            agent_name="r",
            timestamp=100.0,
            tool_name="Read",
            tool_input={"file_path": "a.py"},
        ),
    ]
    result = format_event_trace(events)
    assert "TOOL: Read(a.py)" in result


def test_format_event_trace_tool_result():
    events = [
        ToolCall(
            agent_name="r",
            timestamp=100.0,
            tool_name="Read",
            tool_input={"file_path": "a.py"},
        ),
        RawMessage(
            agent_name="r",
            timestamp=100.5,
            message_type="UserMessage",
            data={"tool_use_result": "file contents"},
        ),
    ]
    result = format_event_trace(events)
    assert "RESULT:" in result


def test_format_event_trace_thinking_truncates():
    long_thought = "x" * 5000
    events = [
        ThinkingOutput(agent_name="r", timestamp=100.0, text=long_thought),
    ]
    result = format_event_trace(events)
    assert "truncated" in result.lower()


def test_format_event_trace_denied():
    events = [
        ToolDenied(
            agent_name="r", timestamp=100.0, tool_name="Bash", command="rm -rf /"
        ),
    ]
    result = format_event_trace(events)
    assert "DENIED" in result


def test_format_event_trace_skips_token_updates():
    events = [
        TokenUpdate(
            agent_name="r",
            timestamp=100.0,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            cost_usd=0.01,
        ),
    ]
    result = format_event_trace(events)
    assert result == "(no behavioral events)"


# ---------------------------------------------------------------------------
# severity_style
# ---------------------------------------------------------------------------


def test_severity_style_high():
    assert severity_style("high") == "bold red"


def test_severity_style_medium():
    assert severity_style("medium") == "yellow"


def test_severity_style_case_insensitive():
    assert severity_style("HIGH") == "bold red"


def test_severity_style_unknown():
    assert severity_style("critical") == "white"


# ---------------------------------------------------------------------------
# system_message_label
# ---------------------------------------------------------------------------


def test_system_message_label_hook_started():
    data = {"subtype": "hook_started", "data": {"hook_name": "pre_tool"}}
    assert system_message_label(data) == "hook started: pre_tool"


def test_system_message_label_init():
    data = {"subtype": "init", "data": {"model": "sonnet", "tools": ["Read", "Grep"]}}
    result = system_message_label(data)
    assert "model=sonnet" in result
    assert "2 tools" in result


def test_system_message_label_unknown():
    data = {"subtype": "something"}
    assert system_message_label(data) == "system: something"


def test_system_message_label_empty():
    assert system_message_label({}) == "system"
