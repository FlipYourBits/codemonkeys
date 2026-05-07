# Agent Runner Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal agent orchestration framework — a single `run_agent()` function that streams SDK events through callbacks, enforces tool restrictions, and returns typed results. Composition via normal Python async.

**Architecture:** Thin wrapper around `claude_agent_sdk.query()`. AgentDefinition is a frozen dataclass. Events are dataclasses emitted via a callback. Display and logging are pluggable subscribers.

**Tech Stack:** Python 3.10+, claude-agent-sdk, pydantic, rich, asyncio

---

### Task 1: Package Skeleton + Types

**Files:**
- Create: `codemonkeys/__init__.py`
- Create: `codemonkeys/core/__init__.py`
- Create: `codemonkeys/core/types.py`
- Test: `tests/test_types.py`

- [ ] **Step 1: Create package directories**

```bash
mkdir -p codemonkeys/core codemonkeys/agents codemonkeys/display tests
```

- [ ] **Step 2: Write the failing test for types**

```python
# tests/test_types.py
from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage


class DummySchema(BaseModel):
    message: str


def test_agent_definition_is_frozen():
    agent = AgentDefinition(
        name="test",
        model="sonnet",
        system_prompt="You are a test agent.",
        tools=["Read", "Grep"],
    )
    assert agent.name == "test"
    assert agent.output_schema is None
    # Frozen — assignment raises
    try:
        agent.name = "changed"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_agent_definition_with_schema():
    agent = AgentDefinition(
        name="reviewer",
        model="haiku",
        system_prompt="Review code.",
        tools=["Read"],
        output_schema=DummySchema,
    )
    assert agent.output_schema is DummySchema


def test_token_usage_defaults():
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_run_result_fields():
    usage = TokenUsage(input_tokens=1000, output_tokens=200)
    result = RunResult(
        output=None,
        text="hello",
        usage=usage,
        cost_usd=0.01,
        duration_ms=500,
    )
    assert result.error is None
    assert result.cost_usd == 0.01
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 4: Write the implementation**

```python
# codemonkeys/__init__.py
"""Codemonkeys — minimal agent orchestration framework."""
```

```python
# codemonkeys/core/__init__.py
"""Core runner, events, and types."""

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage

__all__ = ["AgentDefinition", "RunResult", "TokenUsage"]
```

```python
# codemonkeys/core/types.py
"""Core data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class AgentDefinition:
    """Immutable description of an agent to run."""

    name: str
    model: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    output_schema: type[BaseModel] | None = None


@dataclass
class TokenUsage:
    """Token accounting from a single agent run."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class RunResult:
    """Result returned by run_agent()."""

    output: BaseModel | None
    text: str
    usage: TokenUsage
    cost_usd: float
    duration_ms: int
    error: str | None = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_types.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/__init__.py codemonkeys/core/__init__.py codemonkeys/core/types.py tests/test_types.py
git commit -m "feat: add core types — AgentDefinition, RunResult, TokenUsage"
```

---

### Task 2: Event System

**Files:**
- Create: `codemonkeys/core/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_events.py
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

    # Type check: handler satisfies EventHandler
    h: EventHandler = handler
    h(AgentStarted(agent_name="x", timestamp=0.0, model="sonnet"))
    assert len(received) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/core/events.py
"""Typed events emitted during agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from codemonkeys.core.types import RunResult, TokenUsage


@dataclass
class Event:
    """Base event. All events carry agent_name and timestamp."""

    agent_name: str
    timestamp: float


@dataclass
class AgentStarted(Event):
    """Emitted when an agent run begins."""

    model: str


@dataclass
class ToolCall(Event):
    """Emitted when the agent invokes a tool."""

    tool_name: str
    tool_input: dict


@dataclass
class ToolResult(Event):
    """Emitted when a tool returns a result."""

    tool_name: str
    output: str


@dataclass
class ToolDenied(Event):
    """Emitted when a tool call is blocked by the allowlist."""

    tool_name: str
    command: str


@dataclass
class TokenUpdate(Event):
    """Emitted on each assistant message with updated usage."""

    usage: TokenUsage
    cost_usd: float


@dataclass
class AgentCompleted(Event):
    """Emitted when an agent finishes successfully."""

    result: RunResult


@dataclass
class AgentError(Event):
    """Emitted when an agent fails."""

    error: str


EventHandler = Callable[[Event], None]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/events.py tests/test_events.py
git commit -m "feat: add event system — typed dataclass events with callback handler"
```

---

### Task 3: PreToolUse Hook Builder

**Files:**
- Create: `codemonkeys/core/hooks.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hooks.py
import pytest

from codemonkeys.core.hooks import build_tool_hooks, check_tool_allowed


def test_check_tool_allowed_simple_tools():
    """Non-Bash tools are checked by exact name match."""
    allowed = ["Read", "Grep", "Bash(pytest*)"]
    assert check_tool_allowed("Read", {}, allowed) is True
    assert check_tool_allowed("Grep", {}, allowed) is True
    assert check_tool_allowed("Edit", {}, allowed) is False
    assert check_tool_allowed("Write", {}, allowed) is False


def test_check_tool_allowed_bash_patterns():
    """Bash tools are checked against glob patterns."""
    allowed = ["Read", "Bash(pytest*)", "Bash(ruff*)"]
    assert check_tool_allowed("Bash", {"command": "pytest tests/ -v"}, allowed) is True
    assert check_tool_allowed("Bash", {"command": "ruff check ."}, allowed) is True
    assert check_tool_allowed("Bash", {"command": "rm -rf /"}, allowed) is False
    assert check_tool_allowed("Bash", {"command": ""}, allowed) is False


def test_check_tool_allowed_no_bash_patterns():
    """If 'Bash' is in the list without patterns, all bash commands are allowed."""
    allowed = ["Read", "Bash"]
    assert check_tool_allowed("Bash", {"command": "anything"}, allowed) is True


def test_check_tool_allowed_empty_list():
    """Empty allowlist denies everything."""
    assert check_tool_allowed("Read", {}, []) is False
    assert check_tool_allowed("Bash", {"command": "ls"}, []) is False


@pytest.mark.asyncio
async def test_build_tool_hooks_returns_none_when_no_restrictions():
    """If only simple tool names (no Bash patterns), no hook needed."""
    hooks = build_tool_hooks(["Read", "Grep"])
    # No Bash patterns means no PreToolUse hook needed for Bash enforcement
    # The SDK's allowed_tools handles simple tool restrictions
    assert hooks is None


@pytest.mark.asyncio
async def test_build_tool_hooks_returns_hook_for_bash_patterns():
    """When Bash patterns exist, a PreToolUse hook is built."""
    hooks = build_tool_hooks(["Read", "Bash(pytest*)"])
    assert hooks is not None
    assert "PreToolUse" in hooks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hooks.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/core/hooks.py
"""PreToolUse hook builder — enforces deny-by-default tool allowlist."""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from claude_agent_sdk import HookMatcher, PreToolUseHookInput
from claude_agent_sdk.types import HookEvent, SyncHookJSONOutput

_BASH_PATTERN_RE = re.compile(r"^Bash\((.+)\)$")


def _parse_bash_patterns(tools: list[str]) -> list[str]:
    """Extract glob patterns from Bash(pattern) entries."""
    patterns: list[str] = []
    for spec in tools:
        m = _BASH_PATTERN_RE.match(spec)
        if m:
            patterns.append(m.group(1))
    return patterns


def _has_bare_bash(tools: list[str]) -> bool:
    """Check if 'Bash' (without pattern) is in the allowlist."""
    return "Bash" in tools


def check_tool_allowed(tool_name: str, tool_input: dict[str, Any], allowed_tools: list[str]) -> bool:
    """Check if a tool call is permitted by the allowlist.

    Used both by the hook and for pre-check logic.
    """
    if tool_name == "Bash":
        if _has_bare_bash(allowed_tools):
            return True
        patterns = _parse_bash_patterns(allowed_tools)
        if not patterns:
            return False
        command = tool_input.get("command", "").strip()
        if not command:
            return False
        return any(fnmatch.fnmatch(command, p) for p in patterns)

    # Non-Bash tools: exact name match (ignoring Bash pattern entries)
    simple_tools = {t for t in allowed_tools if not _BASH_PATTERN_RE.match(t) and t != "Bash"}
    return tool_name in simple_tools


OnDenyCallback = Any  # (tool_name: str, command: str) -> None


def build_tool_hooks(
    allowed_tools: list[str],
    on_deny: OnDenyCallback | None = None,
) -> dict[HookEvent, list[HookMatcher]] | None:
    """Build PreToolUse hooks that enforce the tool allowlist.

    Returns None if no Bash pattern enforcement is needed (the SDK's
    allowed_tools/disallowed_tools handles simple tool name restrictions).
    """
    bash_patterns = _parse_bash_patterns(allowed_tools)
    if not bash_patterns:
        return None

    async def _enforce_bash(
        hook_input: PreToolUseHookInput,
        _tool_use_id: str | None,
        _context: Any,
    ) -> SyncHookJSONOutput:
        command = hook_input.tool_input.get("command", "").strip()
        for pattern in bash_patterns:
            if fnmatch.fnmatch(command, pattern):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }
        if on_deny:
            on_deny("Bash", command)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Bash command not allowed. Permitted: {bash_patterns}",
            }
        }

    return {
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[_enforce_bash])]
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hooks.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/hooks.py tests/test_hooks.py
git commit -m "feat: add PreToolUse hook builder — deny-by-default Bash enforcement"
```

---

### Task 4: Runner (`run_agent`)

**Files:**
- Create: `codemonkeys/core/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing test**

This test mocks the SDK's `query()` to avoid needing a real Claude connection:

```python
# tests/test_runner.py
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    ToolCall,
    ToolDenied,
    TokenUpdate,
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


class FakeAssistantMessage:
    def __init__(self, content=None, usage=None):
        self.content = content or []
        self.usage = usage or {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}


class FakeToolUseBlock:
    def __init__(self, name="Read", input=None):
        self.name = name
        self.input = input or {}
        self.type = "tool_use"


class FakeResultMessage:
    def __init__(self, text="", structured_output=None, cost=0.01, duration_ms=500):
        self.subtype = "result"
        self.duration_ms = duration_ms
        self.duration_api_ms = duration_ms
        self.is_error = False
        self.num_turns = 1
        self.session_id = "test-session"
        self.total_cost_usd = cost
        self.usage = {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}
        self.result = text
        self.structured_output = structured_output
        self.stop_reason = "end_turn"


async def _fake_query_simple(**kwargs):
    """Simulates a simple SDK query that reads a file and returns."""
    yield FakeAssistantMessage(
        content=[FakeToolUseBlock(name="Read", input={"file_path": "/foo.py"})],
        usage={"input_tokens": 500, "output_tokens": 100, "total_tokens": 600},
    )
    yield FakeResultMessage(text="All good")


async def _fake_query_structured(**kwargs):
    """Returns structured output."""
    output = {"findings": ["unused import", "missing docstring"]}
    yield FakeResultMessage(
        text="",
        structured_output=output,
        cost=0.02,
        duration_ms=1200,
    )


async def _fake_query_denied_tool(**kwargs):
    """Agent tries to use Bash with a denied command."""
    yield FakeAssistantMessage(
        content=[FakeToolUseBlock(name="Bash", input={"command": "rm -rf /"})],
    )
    yield FakeResultMessage(text="done")


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

    # Check events emitted
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
    """run_agent works fine without an event handler."""
    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_simple):
        result = await run_agent(_make_agent(), "Review the code")

    assert result.text == "All good"


@pytest.mark.asyncio
async def test_run_agent_error_handling():
    async def _fake_query_error(**kwargs):
        yield FakeResultMessage(text="")

    # Make is_error True
    async def _fake_query_real_error(**kwargs):
        msg = FakeResultMessage(text="")
        msg.is_error = True
        msg.result = "Something went wrong"
        yield msg

    events: list[Event] = []
    with patch("codemonkeys.core.runner.query", side_effect=_fake_query_real_error):
        result = await run_agent(
            _make_agent(),
            "Do something",
            on_event=events.append,
        )

    assert result.error is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/core/runner.py
"""Agent runner — thin wrapper around claude_agent_sdk.query()."""

from __future__ import annotations

import json
import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

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
from codemonkeys.core.hooks import build_tool_hooks, check_tool_allowed
from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage

import asyncio
import logging

_log = logging.getLogger(__name__)


def _emit(on_event: EventHandler | None, event: Event) -> None:
    if on_event:
        on_event(event)


def _tool_detail(block: ToolUseBlock) -> str:
    """Format a tool use block for display."""
    name = block.name
    tool_input = block.input or {}
    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "?")
        return f"{name}({path})"
    if name == "Grep":
        return f"Grep('{tool_input.get('pattern', '?')}')"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:80]})" if cmd else "Bash"
    return name


def _extract_simple_tools(tools: list[str]) -> list[str]:
    """Get tool names suitable for SDK allowed_tools (no Bash patterns)."""
    import re
    result = []
    for t in tools:
        if re.match(r"^Bash\(.+\)$", t):
            if "Bash" not in result:
                result.append("Bash")
        else:
            result.append(t)
    return result


async def run_agent(
    agent: AgentDefinition,
    prompt: str,
    on_event: EventHandler | None = None,
) -> RunResult:
    """Run a single agent and return its result.

    Streams SDK events, enforces tool restrictions via PreToolUse hook,
    and emits typed events through the on_event callback.
    """
    now = time.time()
    _emit(on_event, AgentStarted(agent_name=agent.name, timestamp=now, model=agent.model))

    start_time = time.monotonic()

    # Build output_format from Pydantic schema if provided
    output_format: dict[str, Any] | None = None
    if agent.output_schema:
        output_format = {
            "type": "json_schema",
            "schema": agent.output_schema.model_json_schema(),
        }

    # Build on_deny callback for hook
    def _on_deny(tool_name: str, command: str) -> None:
        _emit(
            on_event,
            ToolDenied(
                agent_name=agent.name,
                timestamp=time.time(),
                tool_name=tool_name,
                command=command,
            ),
        )

    # Build SDK options
    sdk_tools = _extract_simple_tools(agent.tools)
    options = ClaudeAgentOptions(
        system_prompt=agent.system_prompt,
        model=agent.model,
        permission_mode="bypassPermissions",
        allowed_tools=sdk_tools,
        hooks=build_tool_hooks(agent.tools, on_deny=_on_deny),
        output_format=output_format,
    )

    # Track state
    last_result: ResultMessage | None = None
    current_usage = TokenUsage(input_tokens=0, output_tokens=0)
    current_cost = 0.0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            usage = message.usage or {}
            current_usage = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            )

            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    _emit(
                        on_event,
                        ToolCall(
                            agent_name=agent.name,
                            timestamp=time.time(),
                            tool_name=block.name,
                            tool_input=block.input or {},
                        ),
                    )

            _emit(
                on_event,
                TokenUpdate(
                    agent_name=agent.name,
                    timestamp=time.time(),
                    usage=current_usage,
                    cost_usd=current_cost,
                ),
            )

        elif isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            if info.status == "rejected":
                resets_at = info.resets_at or 0
                wait = max(resets_at - int(time.time()), 30)
                _log.warning("Rate limited (%s), waiting %ds", info.rate_limit_type, wait)
                await asyncio.sleep(wait)

        elif isinstance(message, ResultMessage):
            last_result = message

    # Build final result
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if last_result is None:
        error_result = RunResult(
            output=None,
            text="",
            usage=current_usage,
            cost_usd=0.0,
            duration_ms=elapsed_ms,
            error="No result message received from SDK",
        )
        _emit(
            on_event,
            AgentError(agent_name=agent.name, timestamp=time.time(), error=error_result.error),
        )
        return error_result

    # Extract cost and usage from final result
    final_usage_raw = last_result.usage or {}
    final_usage = TokenUsage(
        input_tokens=final_usage_raw.get("input_tokens", 0),
        output_tokens=final_usage_raw.get("output_tokens", 0),
        cache_read_tokens=final_usage_raw.get("cache_read_input_tokens", 0),
        cache_creation_tokens=final_usage_raw.get("cache_creation_input_tokens", 0),
    )
    final_cost = last_result.total_cost_usd or 0.0

    # Parse structured output
    parsed_output = None
    if agent.output_schema and last_result.structured_output is not None:
        raw = last_result.structured_output
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            parsed_output = agent.output_schema.model_validate(raw)

    # Check for error
    error = None
    if last_result.is_error:
        error = last_result.result or "Agent returned an error"

    result = RunResult(
        output=parsed_output,
        text=last_result.result or "",
        usage=final_usage,
        cost_usd=final_cost,
        duration_ms=last_result.duration_ms or elapsed_ms,
        error=error,
    )

    if error:
        _emit(on_event, AgentError(agent_name=agent.name, timestamp=time.time(), error=error))
    else:
        _emit(on_event, AgentCompleted(agent_name=agent.name, timestamp=time.time(), result=result))

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/runner.py tests/test_runner.py
git commit -m "feat: add run_agent() — streams SDK events, enforces tools, returns typed results"
```

---

### Task 5: FileLogger

**Files:**
- Create: `codemonkeys/display/__init__.py`
- Create: `codemonkeys/display/logger.py`
- Test: `tests/test_logger.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logger.py
import json
import tempfile
import time
from pathlib import Path

from codemonkeys.core.events import AgentStarted, ToolCall
from codemonkeys.display.logger import FileLogger


def test_file_logger_writes_jsonl():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name

    logger = FileLogger(path)
    logger.handle(AgentStarted(agent_name="test", timestamp=1000.0, model="sonnet"))
    logger.handle(
        ToolCall(
            agent_name="test",
            timestamp=1001.0,
            tool_name="Read",
            tool_input={"file_path": "/foo.py"},
        )
    )
    logger.close()

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["agent_name"] == "test"
    assert first["model"] == "sonnet"

    second = json.loads(lines[1])
    assert second["tool_name"] == "Read"


def test_file_logger_as_event_handler():
    """FileLogger.handle satisfies the EventHandler signature."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name

    logger = FileLogger(path)
    # Use as callback
    event = AgentStarted(agent_name="x", timestamp=time.time(), model="haiku")
    logger.handle(event)
    logger.close()

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_logger.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/display/__init__.py
"""Display and logging subscribers."""
```

```python
# codemonkeys/display/logger.py
"""File logger — writes events as JSONL."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import IO

from codemonkeys.core.events import Event


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
        data = asdict(event)
        data["_type"] = type(event).__name__
        # Handle non-serializable fields (like Pydantic models in RunResult)
        self._file.write(json.dumps(data, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_logger.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/display/__init__.py codemonkeys/display/logger.py tests/test_logger.py
git commit -m "feat: add FileLogger — JSONL event subscriber"
```

---

### Task 6: Rich Live Display

**Files:**
- Create: `codemonkeys/display/live.py`
- Test: `tests/test_live_display.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_live_display.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_live_display.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/display/live.py
"""Rich Live display — real-time agent status cards."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import TokenUsage


@dataclass
class AgentState:
    """Mutable state for one running agent."""

    name: str
    model: str
    current_tool: str = ""
    tool_calls: int = 0
    denied_calls: int = 0
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0))
    cost_usd: float = 0.0
    completed: bool = False
    error: str | None = None


class LiveDisplay:
    """Rich Live display that renders per-agent status cards.

    Usage:
        display = LiveDisplay()
        display.start()
        result = await run_agent(agent, prompt, on_event=display.handle)
        display.stop()
    """

    def __init__(self) -> None:
        self.agents: dict[str, AgentState] = {}
        self._console = Console()
        self._live: Live | None = None

    def start(self) -> None:
        self._live = Live(self._render(), console=self._console, refresh_per_second=8)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def handle(self, event: Event) -> None:
        if isinstance(event, AgentStarted):
            self.agents[event.agent_name] = AgentState(
                name=event.agent_name, model=event.model
            )
        elif isinstance(event, ToolCall):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.current_tool = event.tool_name
                state.tool_calls += 1
        elif isinstance(event, ToolDenied):
            if event.agent_name in self.agents:
                self.agents[event.agent_name].denied_calls += 1
        elif isinstance(event, TokenUpdate):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.usage = event.usage
                state.cost_usd = event.cost_usd
        elif isinstance(event, AgentCompleted):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.completed = True
                state.cost_usd = event.result.cost_usd
                state.usage = event.result.usage
        elif isinstance(event, AgentError):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.error = event.error
                state.completed = True

        if self._live:
            self._live.update(self._render())

    def _render(self) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        total_cost = 0.0
        running = 0

        for state in self.agents.values():
            total_cost += state.cost_usd
            if state.completed:
                # Collapsed summary line
                style = "red" if state.error else "green"
                status = f"[{style}]done[/{style}]"
                if state.error:
                    status = f"[red]error: {state.error[:60]}[/red]"
                line = Text.from_markup(
                    f"  {state.name} [{state.model}] — "
                    f"${state.cost_usd:.4f} — {status}"
                )
                table.add_row(line)
            else:
                running += 1
                tokens_in = f"{state.usage.input_tokens:,}"
                tokens_out = f"{state.usage.output_tokens:,}"
                tool_line = state.current_tool or "..."
                if state.denied_calls:
                    tool_line += f" [red]({state.denied_calls} denied)[/red]"
                content = Text.from_markup(
                    f"  Tool: {tool_line}\n"
                    f"  Tokens: {tokens_in} in / {tokens_out} out  "
                    f"Cost: ${state.cost_usd:.4f}"
                )
                panel = Panel(
                    content,
                    title=f"{state.name} [{state.model}]",
                    title_align="left",
                    border_style="blue",
                )
                table.add_row(panel)

        # Footer
        footer = Text.from_markup(
            f"\n  Totals: ${total_cost:.4f} | {running} agent(s) running"
        )
        table.add_row(footer)
        return table
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_live_display.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/display/live.py tests/test_live_display.py
git commit -m "feat: add LiveDisplay — Rich real-time agent status cards"
```

---

### Task 7: Public API Exports

**Files:**
- Modify: `codemonkeys/__init__.py`
- Modify: `codemonkeys/core/__init__.py`
- Create: `codemonkeys/agents/__init__.py`
- Test: `tests/test_public_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_public_api.py
def test_top_level_imports():
    """Everything needed is importable from the top-level package."""
    from codemonkeys import (
        AgentDefinition,
        RunResult,
        TokenUsage,
        run_agent,
    )
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
    from codemonkeys.display.live import LiveDisplay
    from codemonkeys.display.logger import FileLogger
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL with ImportError (top-level doesn't export run_agent yet)

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/__init__.py
"""Codemonkeys — minimal agent orchestration framework."""

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage
from codemonkeys.core.runner import run_agent

__all__ = ["AgentDefinition", "RunResult", "TokenUsage", "run_agent"]
```

```python
# codemonkeys/agents/__init__.py
"""Agent factory functions."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/__init__.py codemonkeys/agents/__init__.py tests/test_public_api.py
git commit -m "feat: wire up public API exports"
```

---

### Task 8: Example Agent + Integration Smoke Test

**Files:**
- Create: `codemonkeys/agents/python_file_reviewer.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write the agent factory**

```python
# codemonkeys/agents/python_file_reviewer.py
"""Per-file Python reviewer agent."""

from __future__ import annotations

from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition


class Finding(BaseModel):
    file: str
    line: int | None = None
    severity: str
    category: str
    title: str
    description: str
    suggestion: str | None = None


class FileFindings(BaseModel):
    results: list[Finding]


def make_python_file_reviewer(
    files: list[str],
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Create a reviewer agent for one or more Python files."""
    file_list = "\n".join(f"- `{f}`" for f in files)

    return AgentDefinition(
        name=f"reviewer:{','.join(f.split('/')[-1] for f in files)}",
        model=model,
        system_prompt=f"""\
You review Python files for code quality and security issues.

## Files to Review

{file_list}

## Output Format

Return a JSON object with a "results" array containing one Finding per issue found.
Each Finding has: file, line (int or null), severity (high/medium/low/info),
category (quality/security), title, description, suggestion (or null).

## Guardrails

You are a read-only reviewer. Do NOT modify any files.""",
        tools=["Read", "Grep"],
        output_schema=FileFindings,
    )
```

- [ ] **Step 2: Write the integration test**

This test verifies the full composition pattern works (with mocked SDK):

```python
# tests/test_integration.py
"""Integration test — demonstrates parallel agent composition."""

import asyncio
from unittest.mock import patch

import pytest

from codemonkeys.agents.python_file_reviewer import FileFindings, make_python_file_reviewer
from codemonkeys.core.events import AgentCompleted, AgentStarted, Event
from codemonkeys.core.runner import run_agent
from codemonkeys.display.live import LiveDisplay


class FakeResultMessage:
    def __init__(self, structured_output):
        self.subtype = "result"
        self.duration_ms = 800
        self.duration_api_ms = 800
        self.is_error = False
        self.num_turns = 1
        self.session_id = "test"
        self.total_cost_usd = 0.015
        self.usage = {"input_tokens": 2000, "output_tokens": 500, "total_tokens": 2500}
        self.result = ""
        self.structured_output = structured_output
        self.stop_reason = "end_turn"


def _make_fake_query(findings: list[dict]):
    async def _fake(**kwargs):
        yield FakeResultMessage(structured_output={"results": findings})
    return _fake


@pytest.mark.asyncio
async def test_parallel_agents_with_display():
    """Run multiple agents in parallel, collect results, verify composition."""
    agents = [
        make_python_file_reviewer(["src/a.py"], model="haiku"),
        make_python_file_reviewer(["src/b.py"], model="haiku"),
    ]

    findings_a = [{"file": "src/a.py", "line": 10, "severity": "medium", "category": "quality", "title": "unused import", "description": "os is imported but not used", "suggestion": "remove it"}]
    findings_b = []

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
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add codemonkeys/agents/python_file_reviewer.py tests/test_integration.py
git commit -m "feat: add python_file_reviewer agent + integration test for parallel composition"
```

---

### Task 9: Lint, Type Check, Final Verification

**Files:**
- Modify: any files with lint/type issues

- [ ] **Step 1: Run ruff**

```bash
ruff check codemonkeys/ tests/ && ruff format codemonkeys/ tests/
```

Fix any issues found.

- [ ] **Step 2: Run pyright**

```bash
pyright codemonkeys/
```

Fix any type errors. Expected: some `type: ignore` annotations may be needed for SDK types that use `Any`.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint and type errors"
```

---

### Summary

After completing all tasks, the final file layout is:

```
codemonkeys/
    __init__.py              # Public API: AgentDefinition, RunResult, TokenUsage, run_agent
    agents/
        __init__.py
        python_file_reviewer.py
    core/
        __init__.py
        types.py             # AgentDefinition, RunResult, TokenUsage
        events.py            # Event dataclasses + EventHandler type
        hooks.py             # PreToolUse hook builder
        runner.py            # run_agent()
    display/
        __init__.py
        live.py              # LiveDisplay (Rich)
        logger.py            # FileLogger (JSONL)
tests/
    test_types.py
    test_events.py
    test_hooks.py
    test_runner.py
    test_logger.py
    test_live_display.py
    test_public_api.py
    test_integration.py
```

Total: 7 production files, 8 test files. No workflow engine, no registry, no scheduler.
