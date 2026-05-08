# Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract shared formatting from agent and CLI files into `display/formatting.py` and `display/stdout.py`, making agent definitions pure declarations and CLI files thin pipelines.

**Architecture:** Agent files contain only schemas, prompt templates, and factory functions. All formatting (tool calls, event traces, severity styles) lives in `display/formatting.py`. The stdout printer (duplicated in `run_review.py` and `fix.py`) becomes a single module in `display/stdout.py`. CLI files import from shared display modules instead of defining their own formatting.

**Tech Stack:** Python 3.11+, Pydantic, Rich (for display)

---

### Task 1: Create `display/formatting.py` with shared formatting functions

**Files:**
- Create: `codemonkeys/display/formatting.py`
- Test: `tests/test_formatting.py`

This extracts the duplicated formatting logic from `agents/review_auditor.py` (lines 48-123), `run_review.py` (lines 99-105, 264-301), and `fix.py` (lines 38-44) into one module.

- [ ] **Step 1: Write tests for `format_tool_call`**

```python
from codemonkeys.display.formatting import format_tool_call


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.display.formatting'`

- [ ] **Step 3: Write tests for `format_tool_result`**

Add to `tests/test_formatting.py`:

```python
from codemonkeys.display.formatting import format_tool_result


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


def test_format_tool_result_file_truncates_content():
    content = "x" * 2000
    data = {
        "tool_use_result": {
            "file": {"filePath": "big.py", "numLines": 100, "content": content}
        }
    }
    result = format_tool_result(data)
    assert "truncated" in result.lower()


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
```

- [ ] **Step 4: Write tests for `format_event_trace`**

Add to `tests/test_formatting.py`:

```python
from codemonkeys.core.events import (
    RawMessage,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import TokenUsage
from codemonkeys.display.formatting import format_event_trace


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
```

- [ ] **Step 5: Write tests for `severity_style`**

Add to `tests/test_formatting.py`:

```python
from codemonkeys.display.formatting import severity_style


def test_severity_style_high():
    assert severity_style("high") == "bold red"


def test_severity_style_medium():
    assert severity_style("medium") == "yellow"


def test_severity_style_case_insensitive():
    assert severity_style("HIGH") == "bold red"


def test_severity_style_unknown():
    assert severity_style("critical") == "white"
```

- [ ] **Step 6: Write tests for `system_message_label`**

Add to `tests/test_formatting.py`:

```python
from codemonkeys.display.formatting import system_message_label


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
```

- [ ] **Step 7: Implement `display/formatting.py`**

```python
"""Shared formatting — tool calls, event traces, severity styles."""

from __future__ import annotations

import json

from codemonkeys.core.events import (
    Event,
    RawMessage,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
)

THINKING_CAP = 3000
READ_CONTENT_CAP = 1000
RESULT_CAP = 500


def format_tool_call(tool_name: str, tool_input: dict) -> str:
    """Format a tool call as a human-readable string."""
    if tool_name in ("Read", "Edit", "Write"):
        return f"{tool_name}({tool_input.get('file_path', '?')})"
    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "?")
        path = tool_input.get("path", "")
        return f"Grep('{pattern}')" + (f", path={path}" if path else "")
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:100]})"
    return f"{tool_name}({json.dumps(tool_input, default=str)[:200]})"


def format_tool_result(data: dict) -> str:
    """Extract a readable summary from a raw SDK tool result."""
    tur = data.get("tool_use_result", {})
    if isinstance(tur, str):
        if len(tur) <= RESULT_CAP:
            return tur
        return f"{tur[:RESULT_CAP]}... ({len(tur)} total chars)"
    if not isinstance(tur, dict):
        return ""
    f = tur.get("file")
    if isinstance(f, dict) and f.get("filePath"):
        path = f["filePath"]
        num_lines = f.get("numLines", "?")
        content = f.get("content", "")
        if isinstance(content, str) and len(content) > READ_CONTENT_CAP:
            content = (
                content[:READ_CONTENT_CAP]
                + "\n... (truncated FOR THIS AUDIT TRACE ONLY — "
                + f"the reviewer saw the full {len(content)} chars, {num_lines} lines)"
            )
        return f"{path} ({num_lines} lines):\n{content}"
    parts = []
    if "numFiles" in tur:
        parts.append(f"{tur['numFiles']} files")
    if "numLines" in tur:
        parts.append(f"{tur['numLines']} lines")
    return ", ".join(parts) if parts else str(tur)[:RESULT_CAP]


def format_event_trace(events: list[Event]) -> str:
    """Build a timestamped, human-readable trace of agent behavior."""
    if not events:
        return "(empty trace)"

    start_time = events[0].timestamp
    lines: list[str] = []

    for event in events:
        elapsed = event.timestamp - start_time
        ts = f"[{elapsed:5.1f}s]"

        if isinstance(event, ToolCall):
            inp = format_tool_call(event.tool_name, event.tool_input)
            lines.append(f"{ts} TOOL: {inp}")

        elif isinstance(event, RawMessage) and event.message_type == "UserMessage":
            summary = format_tool_result(event.data)
            if summary:
                lines.append(f"       RESULT: {summary}")

        elif isinstance(event, ToolDenied):
            lines.append(f"{ts} DENIED: {event.tool_name}({event.command[:100]})")

        elif isinstance(event, ThinkingOutput) and event.text:
            text = event.text
            if len(text) > THINKING_CAP:
                text = (
                    text[:THINKING_CAP]
                    + "\n... (truncated FOR THIS AUDIT TRACE ONLY — "
                    + f"the reviewer saw {len(event.text)} total chars of its own thinking)"
                )
            lines.append(f"{ts} THINKING:\n{text}")

    return "\n\n".join(lines) if lines else "(no behavioral events)"


def severity_style(severity: str) -> str:
    """Return a Rich style string for a severity level."""
    return {
        "high": "bold red",
        "medium": "yellow",
        "low": "blue",
        "info": "dim",
    }.get(severity.lower(), "white")


def system_message_label(data: dict) -> str:
    """Format a SystemMessage's subtype + key details for display."""
    subtype = data.get("subtype", "")
    inner = data.get("data", {})
    if not isinstance(inner, dict):
        return f"system: {subtype}" if subtype else "system"
    if subtype == "hook_started":
        hook = inner.get("hook_name", "?")
        return f"hook started: {hook}"
    if subtype == "hook_response":
        hook = inner.get("hook_name", "?")
        outcome = inner.get("outcome", "?")
        return f"hook response: {hook} ({outcome})"
    if subtype == "init":
        model = inner.get("model", "?")
        tools = len(inner.get("tools", []))
        return f"init: model={model}, {tools} tools"
    return f"system: {subtype}" if subtype else "system"
```

- [ ] **Step 8: Run all tests**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add codemonkeys/display/formatting.py tests/test_formatting.py
git commit -m "feat: extract shared formatting into display/formatting.py"
```

---

### Task 2: Create `display/stdout.py` with the shared stdout printer

**Files:**
- Create: `codemonkeys/display/stdout.py`
- Test: `tests/test_stdout_printer.py`

This extracts the identical `_make_stdout_printer()` from `run_review.py` (lines 304-407) and `fix.py` (lines 153-241) into one module. The new version imports `format_tool_call`, `format_tool_result`, `system_message_label` from `formatting.py`.

- [ ] **Step 1: Write tests for `make_stdout_printer`**

```python
import io

from rich.console import Console

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    RateLimitHit,
    RawMessage,
    TextOutput,
    ThinkingOutput,
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
    assert "Read(app.py)" in output


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
    assert "$0.005" in output.replace(" ", "").replace("\x1b[0m", "")


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
    assert "rate limit" not in output.lower() or "ok" in output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stdout_printer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.display.stdout'`

- [ ] **Step 3: Implement `display/stdout.py`**

```python
"""Stdout printer — real-time event output for CLI pipelines."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    EventHandler,
    RateLimitHit,
    RawMessage,
    TextOutput,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.display.formatting import (
    format_tool_call,
    format_tool_result,
    system_message_label,
)


def make_stdout_printer(console: Console | None = None) -> EventHandler:
    """Return an event handler that prints agent activity to the console."""
    _console = console or Console(stderr=True)
    _total_cost = 0.0
    _turn = 0
    _last_tool: dict[str, str] = {}

    def _handle(event: Event) -> None:
        nonlocal _total_cost, _turn
        name = event.agent_name

        if isinstance(event, AgentStarted):
            _console.print(f"\n[bold cyan]{name}[/bold cyan] started \\[{event.model}]")

        elif isinstance(event, ThinkingOutput):
            if event.text:
                _console.print(f"  [dim italic]{name} thinking:[/dim italic]")
                for line in event.text.splitlines():
                    _console.print(f"    [dim]{escape(line)}[/dim]")

        elif isinstance(event, TextOutput):
            if event.text:
                _console.print(
                    f"  [dim]{name} text: {len(event.text)} chars[/dim]"
                )

        elif isinstance(event, ToolCall):
            _last_tool[name] = event.tool_name
            detail = format_tool_call(event.tool_name, event.tool_input)
            _console.print(f"  [dim]{name}[/dim] -> {detail}")

        elif isinstance(event, ToolDenied):
            _console.print(
                f"  [red]{name} DENIED: {event.tool_name}({event.command[:80]})[/red]"
            )

        elif isinstance(event, TokenUpdate):
            _turn += 1
            _total_cost += event.cost_usd
            u = event.usage
            _console.print(
                f"  [dim]{name}[/dim] "
                f"turn {_turn}: [bold]${event.cost_usd:.4f}[/bold] "
                f"({u.input_tokens:,} in + {u.cache_read_tokens:,} cache_read "
                f"+ {u.cache_creation_tokens:,} cache_write / {u.output_tokens:,} out) "
                f"| running: ${_total_cost:.4f}",
                highlight=False,
            )

        elif isinstance(event, RateLimitHit):
            if event.status == "rejected":
                _console.print(
                    f"  [red]{name} rate limited ({event.rate_limit_type}) "
                    f"— waiting {event.wait_seconds}s[/red]"
                )

        elif isinstance(event, RawMessage):
            if event.message_type == "SystemMessage":
                label = system_message_label(event.data)
                _console.print(f"  [dim]{name} << {label}[/dim]")
            elif event.message_type == "UserMessage":
                tool = _last_tool.pop(name, "?")
                hint = format_tool_result(event.data)
                suffix = f": {hint}" if hint else ""
                _console.print(
                    f"  [dim]{name} << {tool} result{suffix}[/dim]"
                )
            elif event.message_type == "ResultMessage":
                data = event.data
                cost_val = data.get("total_cost_usd")
                if cost_val is None:
                    cost_val = data.get("cost", 0) or 0
                _console.print(
                    f"  [dim]{name} << result "
                    f"(turns={data.get('num_turns', '?')}, "
                    f"cost=${cost_val:.4f})[/dim]",
                    highlight=False,
                )

        elif isinstance(event, AgentCompleted):
            r = event.result
            secs = r.duration_ms / 1000
            duration = f"{secs / 60:.1f}m" if secs >= 60 else f"{secs:.1f}s"
            _console.print(
                f"[bold green]{name}[/bold green] done "
                f"— ${r.cost_usd:.4f} in {duration}"
            )

        elif isinstance(event, AgentError):
            _console.print(f"[bold red]{name} ERROR: {event.error}[/bold red]")

    return _handle


def fan_out(*handlers: EventHandler) -> EventHandler:
    """Combine multiple event handlers into one."""

    def _handle(event: Event) -> None:
        for h in handlers:
            h(event)

    return _handle
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/test_stdout_printer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/display/stdout.py tests/test_stdout_printer.py
git commit -m "feat: extract shared stdout printer into display/stdout.py"
```

---

### Task 3: Slim down `review_auditor.py` to pure definition

**Files:**
- Modify: `codemonkeys/agents/review_auditor.py`
- Modify: `tests/test_registry.py` (if needed)

Remove all formatting functions from the auditor agent. Change the factory signature from `make_review_auditor(result: RunResult)` to `make_review_auditor(trace: str, findings_json: str, reviewer_name: str, reviewer_model: str, reviewer_tools: str, reviewer_prompt: str)`.

- [ ] **Step 1: Write tests for the new factory signature**

Create `tests/test_review_auditor.py`:

```python
from codemonkeys.agents.review_auditor import ReviewAudit, make_review_auditor


def test_make_review_auditor_returns_definition():
    agent = make_review_auditor(
        trace="[0.0s] TOOL: Read(a.py)",
        findings_json='{"results": []}',
        reviewer_name="python_file_reviewer:a.py",
        reviewer_model="sonnet",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review code.",
    )
    assert agent.name.startswith("auditor:")
    assert agent.model == "sonnet"
    assert agent.output_schema is ReviewAudit
    assert agent.tools == []


def test_make_review_auditor_prompt_contains_trace():
    agent = make_review_auditor(
        trace="[0.0s] TOOL: Read(a.py)\n       RESULT: contents",
        findings_json='{"results": []}',
        reviewer_name="reviewer",
        reviewer_model="sonnet",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review code.",
    )
    assert "TOOL: Read(a.py)" in agent.system_prompt
    assert "RESULT: contents" in agent.system_prompt


def test_make_review_auditor_prompt_contains_reviewer_config():
    agent = make_review_auditor(
        trace="(empty trace)",
        findings_json="null",
        reviewer_name="python_file_reviewer:a.py",
        reviewer_model="haiku",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review Python files.",
    )
    assert "python_file_reviewer:a.py" in agent.system_prompt
    assert "haiku" in agent.system_prompt
    assert "Read, Grep" in agent.system_prompt
    assert "You review Python files." in agent.system_prompt


def test_make_review_auditor_custom_model():
    agent = make_review_auditor(
        trace="(empty)",
        findings_json="null",
        reviewer_name="r",
        reviewer_model="sonnet",
        reviewer_tools="Read",
        reviewer_prompt="prompt",
        model="opus",
    )
    assert agent.model == "opus"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_auditor.py -v`
Expected: FAIL — `TypeError` because the current signature is `make_review_auditor(result: RunResult)`

- [ ] **Step 3: Rewrite `agents/review_auditor.py`**

Replace the entire file:

```python
"""Review auditor agent — verifies reviewer behavior against its mandate."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition

Verdict = Literal["pass", "warn", "fail"]
Category = Literal[
    "file_coverage",
    "tool_compliance",
    "finding_quality",
    "instruction_compliance",
    "hallucination_risk",
]
Severity = Literal["high", "medium", "low", "info"]


class AuditFinding(BaseModel):
    category: Category
    severity: Severity
    title: str
    description: str
    suggestion: str | None = None


class ReviewAudit(BaseModel):
    verdict: Verdict
    findings: list[AuditFinding]
    summary: str


def make_review_auditor(
    trace: str,
    findings_json: str,
    reviewer_name: str,
    reviewer_model: str,
    reviewer_tools: str,
    reviewer_prompt: str,
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Audits a reviewer agent's work to verify behavior compliance."""
    return AgentDefinition(
        name=f"auditor:{reviewer_name}",
        model=model,
        system_prompt=f"""\
You are a review auditor. Analyze the trace below and produce an audit verdict in one pass.

IMPORTANT: The event trace below may show truncated file contents and thinking text.
This truncation is ONLY in this audit view — the reviewer saw the full content.
Do NOT flag truncation as a coverage or hallucination issue.

## Reviewer Configuration

- **Agent:** {reviewer_name}
- **Model:** {reviewer_model}
- **Allowed tools:** {reviewer_tools}

### Reviewer's System Prompt

{reviewer_prompt}

## Event Trace

{trace}

## Structured Output (Findings)

{findings_json}

## Checks

1. **file_coverage** — Did it Read every assigned file?
2. **tool_compliance** — Only used {reviewer_tools}? Any denied calls?
3. **finding_quality** — Findings specific and backed by trace evidence?
4. **instruction_compliance** — Followed its system prompt?
5. **hallucination_risk** — References code/lines not in tool results?

## Output Rules

- **verdict** must be exactly one of: `pass`, `warn`, `fail`
- **category** must be exactly one of: `file_coverage`, `tool_compliance`, `finding_quality`, `instruction_compliance`, `hallucination_risk`
- **severity** must be exactly one of: `high`, `medium`, `low`, `info`
- Include a **suggestion** for each finding (how to fix the reviewer's behavior)
- Produce your verdict immediately. Do not request additional information.""",
        tools=[],
        output_schema=ReviewAudit,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_review_auditor.py tests/test_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/agents/review_auditor.py tests/test_review_auditor.py
git commit -m "refactor: make review_auditor a pure definition, remove formatting"
```

---

### Task 4: Slim down `run_review.py` to use shared display

**Files:**
- Modify: `codemonkeys/run_review.py`

Remove `_make_stdout_printer`, `_severity_style`, `_tool_result_hint`, `_system_message_label`, `_fan_out`. Import from `display/formatting.py` and `display/stdout.py`. Update the auditor creation to use the new `make_review_auditor` signature.

- [ ] **Step 1: Rewrite `run_review.py`**

Replace the entire file:

```python
"""CLI review pipeline — discover files, run parallel reviewers, print findings."""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from codemonkeys.agents.python_file_reviewer import (
    FileFindings,
    Finding,
    make_python_file_reviewer,
)
from codemonkeys.agents.review_auditor import (
    ReviewAudit,
    make_review_auditor,
)
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import RunResult
from codemonkeys.display.formatting import format_event_trace, severity_style
from codemonkeys.display.logger import FileLogger
from codemonkeys.display.stdout import fan_out, make_stdout_printer

BATCH_SIZE = 3
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".tox", ".mypy_cache"}

console = Console()


def _discover_files_explicit(paths: list[str]) -> list[str]:
    resolved = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            console.print(f"[yellow]Warning: {p} does not exist, skipping[/yellow]")
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*.py")):
                if not any(part in EXCLUDE_DIRS for part in child.parts):
                    resolved.append(str(child))
            continue
        if path.suffix != ".py":
            console.print(f"[yellow]Warning: {p} is not a .py file, skipping[/yellow]")
            continue
        resolved.append(str(path))
    return resolved


def _discover_files_diff() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True,
        text=True,
    )
    all_files = set(
        result.stdout.strip().splitlines() + staged.stdout.strip().splitlines()
    )
    return sorted(f for f in all_files if f.endswith(".py") and Path(f).exists())


def _discover_files_repo() -> list[str]:
    files = []
    for p in Path(".").rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        files.append(str(p))
    return sorted(files)


def _batch(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _print_summary(all_findings: list[Finding], total_cost: float) -> None:
    if not all_findings:
        console.print("\n[green]No findings.[/green]")
        return

    high = sum(1 for f in all_findings if f.severity.lower() == "high")
    medium = sum(1 for f in all_findings if f.severity.lower() == "medium")
    low = sum(1 for f in all_findings if f.severity.lower() == "low")

    console.print()
    console.rule(
        f"[bold]{len(all_findings)} findings[/bold] "
        f"([red]{high} high[/red], [yellow]{medium} medium[/yellow], [blue]{low} low[/blue]) "
        f"| Cost: ${total_cost:.4f}",
        style="dim",
    )

    by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}

    for file_path, findings in sorted(by_file.items()):
        table = Table(
            title=file_path,
            title_style="bold",
            show_lines=True,
            expand=True,
            highlight=False,
        )
        table.add_column("Sev", width=6, justify="center", no_wrap=True)
        table.add_column("Line", width=6, justify="right", no_wrap=True)
        table.add_column("Issue", ratio=3)
        table.add_column("Suggestion", ratio=2)

        sorted_findings = sorted(
            findings,
            key=lambda f: (severity_order.get(f.severity.lower(), 9), f.line or 0),
        )

        for finding in sorted_findings:
            style = severity_style(finding.severity)
            sev = f"[{style}]{finding.severity.upper()}[/{style}]"
            line_ref = str(finding.line) if finding.line else ""
            issue = f"[bold]{escape(finding.title)}[/bold]"
            if finding.description:
                issue += f"\n{escape(finding.description)}"
            suggestion = escape(finding.suggestion) if finding.suggestion else ""
            table.add_row(sev, line_ref, issue, suggestion)

        console.print()
        console.print(table)


def _verdict_style(verdict: str) -> str:
    return {"pass": "bold green", "warn": "bold yellow", "fail": "bold red"}.get(
        verdict.lower(), "white"
    )


def _print_audit_results(
    audit_results: list[tuple[str, RunResult]], total_audit_cost: float
) -> None:
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}

    verdicts: list[str] = []
    for _, r in audit_results:
        if isinstance(r.output, ReviewAudit):
            verdicts.append(r.output.verdict.lower())
    passes = verdicts.count("pass")
    warns = verdicts.count("warn")
    fails = verdicts.count("fail")

    console.print()
    console.rule(
        f"[bold]AUDIT[/bold] — "
        f"[bold]{len(audit_results)} audit(s)[/bold] "
        f"([green]{passes} pass[/green], [yellow]{warns} warn[/yellow], "
        f"[red]{fails} fail[/red]) "
        f"| Cost: ${total_audit_cost:.4f}",
        style="magenta",
    )

    for reviewer_name, result in audit_results:
        if result.error:
            console.print(
                f"\n  [red]{reviewer_name} — audit error: {result.error}[/red]"
            )
            continue
        if not isinstance(result.output, ReviewAudit):
            console.print(
                f"\n  [yellow]{reviewer_name} — no structured audit output[/yellow]"
            )
            continue

        audit = result.output
        vstyle = _verdict_style(audit.verdict)

        table = Table(
            title=f"{reviewer_name} — [{vstyle}]{audit.verdict.upper()}[/{vstyle}]",
            title_style="bold",
            caption=audit.summary,
            caption_style="dim",
            show_lines=True,
            expand=True,
            highlight=False,
        )
        table.add_column("Sev", width=6, justify="center", no_wrap=True)
        table.add_column("Category", width=14, no_wrap=True)
        table.add_column("Finding", ratio=3)
        table.add_column("Suggestion", ratio=2)

        if audit.findings:
            sorted_findings = sorted(
                audit.findings,
                key=lambda f: severity_order.get(f.severity.lower(), 9),
            )
            for f in sorted_findings:
                sev_style = severity_style(f.severity)
                sev = f"[{sev_style}]{f.severity.upper()}[/{sev_style}]"
                finding_text = f"[bold]{escape(f.title)}[/bold]"
                if f.description:
                    finding_text += f"\n{escape(f.description)}"
                suggestion = escape(f.suggestion) if f.suggestion else ""
                table.add_row(sev, f.category, finding_text, suggestion)
        else:
            table.add_row(
                "[green]--[/green]", "--", "[green]No issues found[/green]", ""
            )

        console.print()
        console.print(table)


def _make_log_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = Path(".codemonkeys") / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", name)


def _export_outputs(results: list[RunResult], log_dir: Path) -> None:
    for result in results:
        if result.output is None or result.agent_def is None:
            continue
        filename = _safe_filename(result.agent_def.name) + ".json"
        path = log_dir / filename
        path.write_text(result.output.model_dump_json(indent=2) + "\n")
        console.print(f"  [dim]{path}[/dim]")


async def run_review(
    files: list[str], model: str = "sonnet", audit: bool = False
) -> int:
    """Run parallel file reviewers and print findings. Returns exit code."""
    batches = _batch(files, BATCH_SIZE)
    agents = [make_python_file_reviewer(batch, model=model) for batch in batches]

    console.print(
        f"\n[bold]Reviewing {len(files)} file(s) in {len(batches)} batch(es) [{model}][/bold]\n"
    )

    log_dir = _make_log_dir()
    file_logger = FileLogger(log_dir / "events.jsonl")
    stdout_printer = make_stdout_printer()
    on_event = fan_out(stdout_printer, file_logger.handle)

    console.print(f"[dim]Logging to {log_dir}/[/dim]\n")

    try:
        results: list[RunResult] = await asyncio.gather(
            *[
                run_agent(agent, "Review the listed files.", on_event=on_event)
                for agent in agents
            ]
        )
    finally:
        file_logger.close()

    all_findings: list[Finding] = []
    total_cost = 0.0
    for result in results:
        total_cost += result.cost_usd
        if result.error:
            console.print(f"[red]Agent error: {result.error}[/red]")
            continue
        if isinstance(result.output, FileFindings):
            all_findings.extend(result.output.results)

    _export_outputs(results, log_dir)
    _print_summary(all_findings, total_cost)

    if audit:
        successful_results = [r for r in results if not r.error and r.agent_def]
        if not successful_results:
            console.print("\n[yellow]No successful reviews to audit.[/yellow]")
        else:
            console.print(
                f"\n[bold]Auditing {len(successful_results)} review(s) [{model}][/bold]\n"
            )
            audit_logger = FileLogger(log_dir / "audit_events.jsonl")
            audit_on_event = fan_out(stdout_printer, audit_logger.handle)

            try:
                audit_agents = []
                for r in successful_results:
                    ad = r.agent_def
                    assert ad is not None
                    trace = format_event_trace(r.events)
                    findings_json = r.output.model_dump_json(indent=2) if r.output else "null"
                    tools_str = ", ".join(ad.tools) if ad.tools else "(none)"
                    audit_agents.append(
                        make_review_auditor(
                            trace=trace,
                            findings_json=findings_json,
                            reviewer_name=ad.name,
                            reviewer_model=ad.model,
                            reviewer_tools=tools_str,
                            reviewer_prompt=ad.system_prompt,
                            model=model,
                        )
                    )
                audit_results_raw: list[RunResult] = await asyncio.gather(
                    *[
                        run_agent(a, "Audit this review.", on_event=audit_on_event)
                        for a in audit_agents
                    ]
                )
            finally:
                audit_logger.close()

            audit_pairs: list[tuple[str, RunResult]] = []
            total_audit_cost = 0.0
            for review_result, audit_result in zip(
                successful_results, audit_results_raw
            ):
                name = review_result.agent_def.name if review_result.agent_def else "?"
                audit_pairs.append((name, audit_result))
                total_audit_cost += audit_result.cost_usd

            _export_outputs(audit_results_raw, log_dir)
            _print_audit_results(audit_pairs, total_audit_cost)
            total_cost += total_audit_cost

    has_high = any(f.severity.lower() == "high" for f in all_findings)
    return 1 if has_high else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review Python files for quality and security"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--files", nargs="+", metavar="PATH", help="Explicit file paths to review"
    )
    mode.add_argument(
        "--diff", action="store_true", help="Review files changed in git diff"
    )
    mode.add_argument(
        "--repo", action="store_true", help="Review all Python files in the repo"
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["haiku", "sonnet", "opus"],
        help="Model to use (default: sonnet)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run audit agents to verify reviewer behavior",
    )

    args = parser.parse_args()

    if args.files:
        files = _discover_files_explicit(args.files)
    elif args.diff:
        files = _discover_files_diff()
    else:
        files = _discover_files_repo()

    if not files:
        console.print("[yellow]No Python files found to review.[/yellow]")
        sys.exit(0)

    for f in files:
        console.print(f"  [dim]{f}[/dim]")

    exit_code = asyncio.run(run_review(files, model=args.model, audit=args.audit))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add codemonkeys/run_review.py
git commit -m "refactor: slim down run_review.py, import shared display"
```

---

### Task 5: Slim down `fix.py` to use shared display

**Files:**
- Modify: `codemonkeys/fix.py`

Remove `_make_stdout_printer`, `_severity_style`. Import from `display/formatting.py` and `display/stdout.py`.

- [ ] **Step 1: Rewrite `fix.py`**

Replace the entire file:

```python
"""CLI fixer — load findings, pick which to fix, run fixer agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from codemonkeys.agents.fixer import FixItem, FixResult, make_fixer
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import RunResult
from codemonkeys.display.formatting import severity_style
from codemonkeys.display.logger import FileLogger
from codemonkeys.display.stdout import fan_out, make_stdout_printer

console = Console()


def _load_findings(path: Path) -> list[FixItem]:
    """Load findings from a JSON file, auto-detecting format."""
    raw = json.loads(path.read_text())

    items: list[dict] = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if "results" in raw:
            items = raw["results"]
        elif "findings" in raw:
            items = raw["findings"]
        else:
            items = [raw]

    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "title" not in item and "description" not in item:
            continue
        findings.append(
            FixItem(
                file=item.get("file"),
                line=item.get("line"),
                severity=item.get("severity"),
                category=item.get("category"),
                title=item.get("title", item.get("description", "")[:80]),
                description=item.get("description", ""),
                suggestion=item.get("suggestion"),
            )
        )
    return findings


def _display_findings(items: list[FixItem]) -> None:
    table = Table(
        title="Findings",
        title_style="bold",
        show_lines=True,
        expand=True,
        highlight=False,
    )
    table.add_column("#", width=4, justify="right", no_wrap=True)
    table.add_column("Sev", width=6, justify="center", no_wrap=True)
    table.add_column("Location", width=30, no_wrap=True)
    table.add_column("Issue", ratio=3)
    table.add_column("Suggestion", ratio=2)

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    sorted_items = sorted(
        enumerate(items, 1),
        key=lambda x: severity_order.get((x[1].severity or "").lower(), 9),
    )

    for idx, item in sorted_items:
        sev = ""
        if item.severity:
            style = severity_style(item.severity)
            sev = f"[{style}]{item.severity.upper()}[/{style}]"

        loc = ""
        if item.file:
            loc = escape(item.file)
            if item.line:
                loc += f":{item.line}"

        issue = f"[bold]{escape(item.title)}[/bold]"
        if item.description and item.description != item.title:
            issue += f"\n{escape(item.description)}"

        suggestion = escape(item.suggestion) if item.suggestion else ""
        table.add_row(str(idx), sev, loc, issue, suggestion)

    console.print(table)


def _prompt_selection(count: int) -> list[int] | None:
    """Prompt user to select findings. Returns 0-based indices or None to quit."""
    console.print()
    response = console.input(
        "[bold]Fix:[/bold] [dim][a]ll, [1,2,3] specific, [q]uit[/dim] > "
    )
    response = response.strip().lower()

    if response in ("q", "quit", ""):
        return None
    if response in ("a", "all"):
        return list(range(count))

    indices = []
    for part in response.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
            if 1 <= n <= count:
                indices.append(n - 1)
            else:
                console.print(f"[yellow]Skipping {n} — out of range[/yellow]")
        except ValueError:
            console.print(f"[yellow]Skipping '{part}' — not a number[/yellow]")
    return indices if indices else None


def _print_result(result: RunResult) -> None:
    if result.error:
        console.print(f"\n[red]Fixer error: {result.error}[/red]")
        return

    if not isinstance(result.output, FixResult):
        console.print("\n[yellow]No structured result from fixer.[/yellow]")
        return

    fix = result.output
    console.print()
    if fix.applied:
        console.print(f"[green]Applied ({len(fix.applied)}):[/green]")
        for title in fix.applied:
            console.print(f"  [green]+[/green] {escape(title)}")
    if fix.skipped:
        console.print(f"[yellow]Skipped ({len(fix.skipped)}):[/yellow]")
        for reason in fix.skipped:
            console.print(f"  [yellow]-[/yellow] {escape(reason)}")
    console.print(f"\n[dim]{fix.summary}[/dim]")


async def run_fix(
    items: list[FixItem], model: str = "opus"
) -> RunResult:
    """Run the fixer agent on selected findings."""
    agent = make_fixer(items, model=model)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = Path(".codemonkeys") / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)

    file_logger = FileLogger(log_dir / "fix_events.jsonl")
    stdout_printer = make_stdout_printer()
    on_event = fan_out(stdout_printer, file_logger.handle)

    console.print(f"[dim]Logging to {log_dir}/[/dim]\n")

    try:
        result = await run_agent(
            agent, "Apply the fixes described in your system prompt.", on_event=on_event
        )
    finally:
        file_logger.close()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix code issues from review/audit findings"
    )
    parser.add_argument(
        "findings",
        type=Path,
        help="Path to findings JSON file",
    )
    parser.add_argument(
        "--model",
        default="opus",
        choices=["haiku", "sonnet", "opus"],
        help="Model to use (default: opus)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="fix_all",
        help="Fix all findings without prompting",
    )

    args = parser.parse_args()

    if not args.findings.exists():
        console.print(f"[red]File not found: {args.findings}[/red]")
        sys.exit(1)

    items = _load_findings(args.findings)
    if not items:
        console.print("[yellow]No findings found in file.[/yellow]")
        sys.exit(0)

    _display_findings(items)

    if args.fix_all:
        selected_indices = list(range(len(items)))
    else:
        selected_indices = _prompt_selection(len(items))

    if selected_indices is None:
        console.print("[dim]Nothing selected.[/dim]")
        sys.exit(0)

    selected = [items[i] for i in selected_indices]
    console.print(
        f"\n[bold]Fixing {len(selected)} finding(s) [{args.model}][/bold]"
    )

    result = asyncio.run(run_fix(selected, model=args.model))
    _print_result(result)

    sys.exit(1 if result.error else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Lint and format**

Run: `uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 4: Commit**

```bash
git add codemonkeys/fix.py
git commit -m "refactor: slim down fix.py, import shared display"
```

---

### Task 6: Update `display/logger.py` to use shared formatting

**Files:**
- Modify: `codemonkeys/display/logger.py`

The `FileLogger` currently uses `dataclasses.asdict` which has the same Pydantic serialization issue as the orchestrator. Update it to use `json_safe` from `core/types.py`.

- [ ] **Step 1: Update `display/logger.py`**

```python
"""File logger — writes events as JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO

from codemonkeys.core.events import Event
from codemonkeys.core.types import json_safe


class FileLogger:
    """Writes events as JSON lines to a file.

    Usage:
        logger = FileLogger("run.jsonl")
        result = await run_agent(agent, prompt, on_event=logger.handle)
        logger.close()
    """

    def __init__(self, path: str | Path) -> None:
        self._file: IO[str] = open(path, "a")

    def handle(self, event: Event) -> None:
        data = json_safe(event)
        data["_type"] = type(event).__name__
        self._file.write(json.dumps(data, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
```

- [ ] **Step 2: Run existing logger tests**

Run: `uv run pytest tests/test_logger.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add codemonkeys/display/logger.py
git commit -m "fix: use json_safe in FileLogger for proper Pydantic serialization"
```

---

### Task 7: Final verification — full test suite, lint, type check

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check --fix . && uv run ruff format .`
Expected: No errors

- [ ] **Step 3: Type check**

Run: `uv run pyright codemonkeys/display/formatting.py codemonkeys/display/stdout.py codemonkeys/agents/review_auditor.py`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 4: Verify no remaining duplicated formatting**

Run: `grep -rn "def _severity_style\|def _make_stdout_printer\|def _format_tool_input\|def _tool_result_hint\|def _system_message_label" codemonkeys/`
Expected: No matches — all duplicates removed

- [ ] **Step 5: Commit any fixups**

```bash
git add -A
git commit -m "chore: final cleanup after agent refactor"
```
