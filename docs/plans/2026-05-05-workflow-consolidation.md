# Workflow Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `run_review.py` monolith and `workflows/` engine into a single system by rebuilding the agent runner and display, porting NLP triage, and deleting dead code.

**Architecture:** Rebuild `AgentRunner` to emit events instead of owning a display. Build a unified `WorkflowDisplay` that subscribes to those events. Port NLP triage into the phase library. Shrink `run_review.py` to a thin CLI wrapper. Delete TUI and duplicates.

**Tech Stack:** Python 3.12, claude_agent_sdk, Rich (Live, Table, Text, Group), Pydantic, asyncio

---

### Task 1: Add `RunResult` dataclass and `log_dir` to `WorkflowContext`

**Files:**
- Create: `codemonkeys/core/run_result.py`
- Modify: `codemonkeys/workflows/phases.py:30-36`
- Test: `tests/test_run_result.py`

- [ ] **Step 1: Write the failing test for `RunResult`**

```python
# tests/test_run_result.py
from __future__ import annotations

from codemonkeys.core.run_result import RunResult


class TestRunResult:
    def test_basic_construction(self) -> None:
        r = RunResult(
            text="hello",
            structured={"key": "value"},
            usage={"input_tokens": 100, "output_tokens": 50},
            cost=0.01,
            duration_ms=1234,
        )
        assert r.text == "hello"
        assert r.structured == {"key": "value"}
        assert r.cost == 0.01
        assert r.duration_ms == 1234

    def test_defaults(self) -> None:
        r = RunResult(text="", structured=None, usage={}, cost=None, duration_ms=0)
        assert r.structured is None
        assert r.cost is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_result.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.core.run_result'`

- [ ] **Step 3: Write `RunResult`**

```python
# codemonkeys/core/run_result.py
"""Result dataclass returned by AgentRunner.run_agent()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RunResult:
    text: str
    structured: dict[str, Any] | None
    usage: dict[str, Any]
    cost: float | None
    duration_ms: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_result.py -v`
Expected: PASS

- [ ] **Step 5: Add `log_dir` field to `WorkflowContext`**

In `codemonkeys/workflows/phases.py`, add the import and field:

```python
# Add to imports
from pathlib import Path

# Add field to WorkflowContext dataclass (after emitter):
log_dir: Path | None = None
```

- [ ] **Step 6: Run existing tests to verify nothing breaks**

Run: `uv run pytest tests/test_engine.py tests/test_action_phases.py tests/test_review_phases.py -v`
Expected: all PASS — new field has a default

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/core/run_result.py tests/test_run_result.py codemonkeys/workflows/phases.py
git commit -m "feat: add RunResult dataclass and log_dir to WorkflowContext"
```

---

### Task 2: Add `model` and `files_label` to `AgentStartedPayload`

**Files:**
- Modify: `codemonkeys/workflows/events.py:38-40`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
class TestAgentStartedPayloadExtended:
    def test_model_and_files_label_fields(self) -> None:
        payload = AgentStartedPayload(
            agent_name="reviewer",
            task_id="abc",
            model="sonnet",
            files_label="a.py, b.py",
        )
        assert payload.model == "sonnet"
        assert payload.files_label == "a.py, b.py"

    def test_model_and_files_label_default_empty(self) -> None:
        payload = AgentStartedPayload(agent_name="reviewer", task_id="abc")
        assert payload.model == ""
        assert payload.files_label == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py::TestAgentStartedPayloadExtended -v`
Expected: FAIL — `unexpected keyword argument 'model'`

- [ ] **Step 3: Add fields to `AgentStartedPayload`**

In `codemonkeys/workflows/events.py`, modify `AgentStartedPayload`:

```python
class AgentStartedPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent that started")
    task_id: str = Field(description="Unique ID for this agent task")
    model: str = Field(default="", description="Model used by this agent")
    files_label: str = Field(default="", description="Files being processed")
```

- [ ] **Step 4: Run all event tests to verify nothing breaks**

Run: `uv run pytest tests/test_events.py tests/test_new_events.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/events.py tests/test_events.py
git commit -m "feat: add model and files_label to AgentStartedPayload"
```

---

### Task 3: Rebuild `AgentRunner`

**Files:**
- Rewrite: `codemonkeys/core/runner.py`
- Test: `tests/test_runner.py`

The new runner emits events instead of owning a display, writes debug logs, and returns `RunResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runner.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


async def _fake_query_stream(*messages):
    """Build an async generator that yields the given messages."""

    async def _gen(**kwargs):
        for msg in messages:
            yield msg

    return _gen


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
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
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
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
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
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
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
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert isinstance(result, RunResult)


class TestAgentRunnerLogging:
    @pytest.mark.asyncio
    async def test_writes_log_files(self, tmp_path: Path) -> None:
        assistant = _make_assistant_message()
        result_msg = _make_result_message(
            result="done", structured_output={"out": 1}
        )

        async def fake_query(**kwargs):
            yield assistant
            yield result_msg

        runner = AgentRunner(cwd="/tmp/test", log_dir=tmp_path)
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
        ):
            await runner.run_agent(
                _make_agent(), "do stuff", log_name="test_log"
            )

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
        with patch("codemonkeys.core.runner.query", fake_query), patch(
            "codemonkeys.core.runner.restrict"
        ):
            result = await runner.run_agent(_make_agent(), "do stuff")

        assert isinstance(result, RunResult)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — current runner has different API

- [ ] **Step 3: Rewrite `core/runner.py`**

```python
# codemonkeys/core/runner.py
"""Reusable agent runner with event emission, debug logging, and filesystem sandboxing."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    ToolUseBlock,
    query,
)

from codemonkeys.core.run_result import RunResult
from codemonkeys.core.sandbox import restrict
from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
)


def _tool_detail(block: ToolUseBlock) -> str:
    name = block.name
    tool_input = block.input or {}
    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "?")
        return f"{name}({path})"
    if name == "Grep":
        return f"Grep('{tool_input.get('pattern', '?')}')"
    if name == "Glob":
        return f"Glob({tool_input.get('pattern', tool_input.get('path', '?'))})"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:80]})" if cmd else "Bash"
    return name


def _serialize_message(message: Any) -> dict[str, Any]:
    """Serialize an SDK message to a JSON-safe dict for logging."""
    entry: dict[str, Any] = {"type": type(message).__name__}
    if isinstance(message, AssistantMessage):
        entry["usage"] = message.usage
        blocks = []
        for b in message.content:
            if isinstance(b, ToolUseBlock):
                blocks.append({"type": "tool_use", "name": b.name, "input": b.input})
            elif hasattr(b, "text"):
                blocks.append({"type": "text", "text": b.text[:500]})
            elif hasattr(b, "thinking"):
                blocks.append({"type": "thinking", "thinking": b.thinking[:500]})
        entry["content"] = blocks
    elif isinstance(message, ResultMessage):
        entry["result"] = (getattr(message, "result", "") or "")[:500]
        entry["usage"] = message.usage
        entry["cost"] = getattr(message, "total_cost_usd", None)
        entry["duration_ms"] = getattr(message, "duration_ms", 0)
    elif isinstance(message, TaskStartedMessage):
        entry["task_id"] = message.task_id
        entry["description"] = message.description
    elif isinstance(message, TaskProgressMessage):
        entry["task_id"] = message.task_id
        usage = message.usage
        entry["usage"] = dict(usage) if isinstance(usage, dict) else {
            "total_tokens": getattr(usage, "total_tokens", 0),
            "tool_uses": getattr(usage, "tool_uses", 0),
        }
    elif isinstance(message, TaskNotificationMessage):
        entry["task_id"] = message.task_id
        usage = message.usage
        if usage:
            entry["usage"] = dict(usage) if isinstance(usage, dict) else {
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
    return entry


class AgentRunner:
    """Runs agents with event emission, debug logging, and filesystem sandboxing.

    Usage::

        runner = AgentRunner(cwd="/path/to/project", emitter=emitter, log_dir=log_dir)
        result = await runner.run_agent(agent, "Review: src/main.py", log_name="review")
    """

    def __init__(
        self,
        cwd: str = ".",
        emitter: EventEmitter | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self.cwd = cwd
        self._emitter = emitter
        self._log_dir = log_dir

    def _emit(self, event_type: EventType, payload: Any) -> None:
        if self._emitter:
            self._emitter.emit(event_type, payload)

    def _log_path(self, log_name: str) -> Path | None:
        if not self._log_dir:
            return None
        safe = log_name.replace("/", "__").replace("\\", "__").replace(" ", "_")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        return self._log_dir / f"{safe}_{ts}.log"

    async def run_agent(
        self,
        agent: AgentDefinition,
        prompt: str,
        *,
        output_format: dict[str, Any] | None = None,
        log_name: str = "agent",
    ) -> RunResult:
        restrict(self.cwd)

        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=self.cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=agent.tools or [],
            disallowed_tools=agent.disallowedTools or [],
            output_format=output_format,
        )

        self._emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(
                agent_name=log_name,
                task_id=log_name,
                model=agent.model or "sonnet",
                files_label="",
            ),
        )

        log_file = self._log_path(log_name)
        total_tokens = 0
        tool_calls = 0
        current_tool = ""
        last_result: ResultMessage | None = None
        subagent_tokens: dict[str, int] = {}
        has_subagents = False
        start_time = time.monotonic()

        def _log(entry: dict[str, Any]) -> None:
            if not log_file:
                return
            entry["ts"] = datetime.now(timezone.utc).isoformat()
            with open(log_file, "a") as f:
                f.write(json.dumps(entry, default=repr) + "\n")

        _log({
            "event": "agent_start",
            "name": log_name,
            "description": agent.description,
            "model": agent.model,
            "tools": agent.tools,
            "prompt_length": len(agent.prompt),
            "user_prompt": prompt,
        })

        async def _prompt_gen():
            yield {"type": "user", "message": {"role": "user", "content": prompt}}

        async for message in query(prompt=_prompt_gen(), options=options):
            _log(_serialize_message(message))

            if isinstance(message, AssistantMessage):
                if not has_subagents:
                    usage = message.usage or {}
                    turn_tokens = usage.get("total_tokens", 0) or (
                        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    )
                    total_tokens += turn_tokens

                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name != "Agent":
                        tool_calls += 1
                        current_tool = _tool_detail(block)

                self._emit(
                    EventType.AGENT_PROGRESS,
                    AgentProgressPayload(
                        agent_name=log_name,
                        task_id=log_name,
                        tokens=total_tokens,
                        tool_calls=tool_calls,
                        current_tool=current_tool,
                    ),
                )

            elif isinstance(message, TaskStartedMessage):
                has_subagents = True
                subagent_tokens[message.task_id] = 0

            elif isinstance(message, TaskProgressMessage):
                usage = message.usage
                tokens = (
                    usage["total_tokens"]
                    if isinstance(usage, dict)
                    else getattr(usage, "total_tokens", 0)
                )
                subagent_tokens[message.task_id] = tokens
                total_tokens = sum(subagent_tokens.values())
                tools = (
                    usage.get("tool_uses", 0)
                    if isinstance(usage, dict)
                    else getattr(usage, "tool_uses", 0)
                )
                self._emit(
                    EventType.AGENT_PROGRESS,
                    AgentProgressPayload(
                        agent_name=log_name,
                        task_id=log_name,
                        tokens=total_tokens,
                        tool_calls=tools,
                        current_tool="",
                    ),
                )

            elif isinstance(message, TaskNotificationMessage):
                usage = message.usage
                if usage:
                    final = (
                        usage["total_tokens"]
                        if isinstance(usage, dict)
                        else getattr(usage, "total_tokens", 0)
                    )
                    subagent_tokens[message.task_id] = final
                    total_tokens = sum(subagent_tokens.values())

            elif isinstance(message, ResultMessage):
                last_result = message
                usage = message.usage or {}
                total_tokens = usage.get("total_tokens", 0) or (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Extract structured output
        structured: dict[str, Any] | None = None
        if last_result:
            raw = getattr(last_result, "structured_output", None)
            if raw is not None:
                if isinstance(raw, str):
                    try:
                        structured = json.loads(raw)
                    except json.JSONDecodeError:
                        structured = None
                elif isinstance(raw, dict):
                    structured = raw

        result = RunResult(
            text=getattr(last_result, "result", "") or "" if last_result else "",
            structured=structured,
            usage=last_result.usage or {} if last_result else {},
            cost=getattr(last_result, "total_cost_usd", None) if last_result else None,
            duration_ms=getattr(last_result, "duration_ms", elapsed_ms)
            if last_result
            else elapsed_ms,
        )

        self._emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(
                agent_name=log_name,
                task_id=log_name,
                tokens=total_tokens,
            ),
        )

        # Write debug markdown
        if log_file:
            structured_out = ""
            if structured:
                structured_out = json.dumps(structured, indent=2, default=repr)
            elif result.text:
                structured_out = result.text

            debug_path = log_file.with_suffix(".md")
            with open(debug_path, "w") as f:
                f.write(f"# Agent: {log_name}\n\n")
                f.write(f"**Model:** {agent.model or 'sonnet'}\n")
                f.write(f"**Tools:** {', '.join(agent.tools or [])}\n\n")
                f.write("## System Prompt\n\n```\n")
                f.write(agent.prompt)
                f.write("\n```\n\n## User Prompt\n\n```\n")
                f.write(prompt)
                f.write("\n```\n\n## Structured Output\n\n```json\n")
                f.write(structured_out or "(no output)")
                f.write("\n```\n")

        return result
```

- [ ] **Step 4: Run runner tests**

Run: `uv run pytest tests/test_runner.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/runner.py tests/test_runner.py
git commit -m "feat: rebuild AgentRunner with event emission, logging, and RunResult"
```

---

### Task 4: Update phase library to use new `AgentRunner` API

**Files:**
- Modify: `codemonkeys/workflows/phase_library/review.py`
- Modify: `codemonkeys/workflows/phase_library/action.py`
- Test: `tests/test_review_phases.py`
- Test: `tests/test_action_phases.py`

The new runner returns `RunResult` with `structured` already parsed. Phases no longer need `getattr(runner.last_result, "structured_output")` / `json.loads` boilerplate.

- [ ] **Step 1: Update `phase_library/review.py`**

Key changes to every phase function:
- Construct runner with `AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)`
- `run_agent()` now returns `RunResult` instead of a raw string
- Use `result.structured` instead of `getattr(runner.last_result, "structured_output", None)` + `json.loads`
- Pass `log_name=` to `run_agent()` for debug log filenames

Update `_run_file_batch`:

```python
async def _run_file_batch(
    batch_files: list[str],
    model: str,
    ctx: WorkflowContext,
    semaphore: asyncio.Semaphore,
) -> FileFindings:
    async with semaphore:
        config = ctx.config
        runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
        agent = make_python_file_reviewer(batch_files, model=model)

        prompt = f"Review: {', '.join(batch_files)}"
        if config.mode == "diff":
            full_diff = ctx.phase_results["discover"].get("diff_hunks", "")
            hunks = _extract_hunks_for_files(full_diff, batch_files)
            call_graph = ctx.phase_results["discover"].get("call_graph", "")
            prompt = (
                DIFF_CONTEXT_TEMPLATE.format(diff_hunks=hunks, call_graph=call_graph)
                + f"\n\nReview: {', '.join(batch_files)}"
            )

        output_format: dict[str, Any] = {
            "type": "json_schema",
            "schema": FileFindings.model_json_schema(),
        }
        result = await runner.run_agent(
            agent, prompt, output_format=output_format,
            log_name=f"review_batch__{batch_files[0]}",
        )

        if result.structured:
            return FileFindings.model_validate(result.structured)
        try:
            return FileFindings.model_validate_json(result.text)
        except Exception:
            return FileFindings(
                file=batch_files[0], summary="Could not parse output", findings=[]
            )
```

Apply the same pattern to `architecture_review`, `_run_doc_reviewer`, and `spec_compliance_review` — replace `runner.last_result` access with `result.structured`.

- [ ] **Step 2: Update `phase_library/action.py`**

Update `_fix_one_file` to use the new runner API:

```python
async def _fix_one_file(
    request: FixRequest,
    cwd: str,
    emitter: Any,
    semaphore: asyncio.Semaphore,
    log_dir: Path | None = None,
) -> FixResult:
    async with semaphore:
        if emitter:
            emitter.emit(
                EventType.FIX_PROGRESS,
                FixProgressPayload(file=request.file, status="started"),
            )

        runner = AgentRunner(cwd=cwd, emitter=emitter, log_dir=log_dir)
        findings_json = request.model_dump_json(indent=2)
        agent = make_python_code_fixer(request.file, findings_json)
        output_format = {
            "type": "json_schema",
            "schema": FixResult.model_json_schema(),
        }
        result = await runner.run_agent(
            agent, f"Fix findings in {request.file}",
            output_format=output_format,
            log_name=f"fix__{request.file}",
        )

        if result.structured:
            fix_result = FixResult.model_validate(result.structured)
        else:
            fix_result = FixResult(
                file=request.file, fixed=[], skipped=["Could not parse agent output"]
            )

        if emitter:
            status = "completed" if fix_result.fixed else "failed"
            emitter.emit(
                EventType.FIX_PROGRESS,
                FixProgressPayload(file=request.file, status=status),
            )

        return fix_result
```

Update `fix()` to pass `log_dir`:

```python
async def fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
    fix_requests: list[FixRequest] = ctx.phase_results["triage"]["fix_requests"]
    config = ctx.config
    semaphore = asyncio.Semaphore(config.max_concurrent)

    tasks = [
        _fix_one_file(request, ctx.cwd, ctx.emitter, semaphore, ctx.log_dir)
        for request in fix_requests
    ]
    results = await asyncio.gather(*tasks)
    return {"fix_results": list(results)}
```

- [ ] **Step 3: Update test mocks to match new API**

The existing tests mock `AgentRunner` with `mock_runner.run_agent = AsyncMock(return_value="{}")` and `mock_runner.last_result`. Update them to return `RunResult` instead.

In `tests/test_review_phases.py`, update the mock pattern:

```python
from codemonkeys.core.run_result import RunResult

# Replace old mock pattern:
#   mock_runner.run_agent = AsyncMock(return_value="{}")
#   mock_runner.last_result = MagicMock(structured_output=...)
# With new pattern:
mock_runner = MagicMock()
mock_runner.run_agent = AsyncMock(return_value=RunResult(
    text="{}",
    structured=FileFindings(file="a.py", summary="test", findings=[]).model_dump(),
    usage={"input_tokens": 100, "output_tokens": 50},
    cost=None,
    duration_ms=500,
))
```

Apply this to every test class in `test_review_phases.py` and `test_action_phases.py` that mocks `AgentRunner`.

- [ ] **Step 4: Run all phase tests**

Run: `uv run pytest tests/test_review_phases.py tests/test_action_phases.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/review.py codemonkeys/workflows/phase_library/action.py tests/test_review_phases.py tests/test_action_phases.py
git commit -m "refactor: update phase library to use new AgentRunner API"
```

---

### Task 5: Port NLP triage into `phase_library/action.py`

**Files:**
- Modify: `codemonkeys/workflows/phase_library/action.py`
- Test: `tests/test_action_phases.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_action_phases.py`:

```python
class TestNLPTriage:
    @pytest.mark.asyncio
    async def test_string_input_dispatches_nlp_agent(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text='[{"file": "a.py", "finding_indices": [1]}]',
                structured=None,
                usage={},
                cost=None,
                duration_ms=100,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[_make_finding(file="a.py", severity="high")],
                        )
                    ]
                },
            },
        )
        ctx.user_input = "fix everything"

        with patch(
            "codemonkeys.workflows.phase_library.action.AgentRunner",
            return_value=mock_runner,
        ):
            result = await triage(ctx)

        assert mock_runner.run_agent.call_count == 1
        assert len(result["fix_requests"]) == 1
        assert result["fix_requests"][0].file == "a.py"

    @pytest.mark.asyncio
    async def test_list_input_passes_through(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        manual = [FixRequest(file="x.py", findings=[_make_finding(file="x.py")])]
        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[_make_finding()],
                        )
                    ]
                },
            },
        )
        ctx.user_input = manual
        result = await triage(ctx)
        assert result["fix_requests"] == manual
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_action_phases.py::TestNLPTriage -v`
Expected: FAIL — string user_input currently passes through without NLP handling

- [ ] **Step 3: Add `_nlp_triage()` to `action.py`**

Add these imports at the top of `action.py`:

```python
from claude_agent_sdk import AgentDefinition
from codemonkeys.core.run_result import RunResult
```

Add the helper function before `triage()`:

```python
async def _nlp_triage(
    user_text: str,
    all_findings: dict[str, list[Finding]],
    ctx: WorkflowContext,
) -> list[FixRequest]:
    """Use a haiku agent to translate natural language into fix selections."""
    flat_findings = []
    for file, findings in all_findings.items():
        for f in findings:
            flat_findings.append(f)

    findings_summary = json.dumps(
        [{"idx": i + 1, **f.model_dump()} for i, f in enumerate(flat_findings)],
        indent=2,
    )

    triage_prompt = f"""\
Here are the code review findings:

{findings_summary}

The user said: "{user_text}"

Based on the user's instruction, return a JSON array of objects, each with:
- "file": the file path
- "finding_indices": array of 1-based finding indices to fix in that file

Group findings by file. Only include findings the user wants to fix.
Return ONLY the JSON array, no explanation."""

    agent = AgentDefinition(
        description="Triage filter",
        prompt="You translate natural language triage instructions into structured selections. Return only valid JSON.",
        model="haiku",
        tools=[],
        permissionMode="dontAsk",
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    result = await runner.run_agent(agent, triage_prompt, log_name="nlp_triage")

    raw = result.text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        selections = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        selections = None

    if selections is None:
        fix_requests = []
        for file, findings in all_findings.items():
            if findings:
                fix_requests.append(FixRequest(file=file, findings=findings))
        return fix_requests

    fix_requests = []
    for sel in selections:
        file_path = sel["file"]
        indices = sel.get("finding_indices", [])
        matched = [
            flat_findings[i - 1]
            for i in indices
            if 1 <= i <= len(flat_findings)
        ]
        if matched:
            fix_requests.append(FixRequest(file=file_path, findings=matched))

    return fix_requests
```

- [ ] **Step 4: Update `triage()` to dispatch NLP triage for string input**

In the `triage()` function, modify the `ctx.user_input` handling block:

```python
    if ctx.user_input is not None:
        if isinstance(ctx.user_input, str):
            fix_requests = await _nlp_triage(ctx.user_input, all_findings, ctx)
            return {"fix_requests": fix_requests}
        return {"fix_requests": ctx.user_input}
```

- [ ] **Step 5: Run triage tests**

Run: `uv run pytest tests/test_action_phases.py -v`
Expected: all PASS (existing tests + new NLP tests)

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/workflows/phase_library/action.py tests/test_action_phases.py
git commit -m "feat: port NLP triage into phase library"
```

---

### Task 6: Build unified `WorkflowDisplay`

**Files:**
- Create: `codemonkeys/workflows/display.py`
- Test: `tests/test_display.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_display.py
from __future__ import annotations

from io import StringIO

from rich.console import Console

from codemonkeys.workflows.display import WorkflowDisplay
from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    TriageReadyPayload,
    WorkflowErrorPayload,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def _make_workflow() -> Workflow:
    async def noop(ctx: WorkflowContext) -> dict:
        return {}

    return Workflow(
        name="test",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="triage", phase_type=PhaseType.GATE, execute=noop),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=noop),
        ],
    )


class TestWorkflowDisplayPhases:
    def test_initial_state_all_pending(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        assert all(s == "pending" for s in display._phase_status.values())

    def test_phase_started_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        assert display._phase_status["discover"] == "running"

    def test_phase_completed_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        emitter.emit(
            EventType.PHASE_COMPLETED,
            PhaseCompletedPayload(phase="discover", workflow="test"),
        )
        assert display._phase_status["discover"] == "done"


class TestWorkflowDisplayAgents:
    def test_agent_started_creates_card(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(
                agent_name="reviewer",
                task_id="r1",
                model="sonnet",
                files_label="a.py",
            ),
        )
        assert "r1" in display._agents
        assert display._agents["r1"]["model"] == "sonnet"

    def test_agent_progress_updates_tokens(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.AGENT_PROGRESS,
            AgentProgressPayload(
                agent_name="r",
                task_id="r1",
                tokens=5000,
                tool_calls=3,
                current_tool="Read(a.py)",
            ),
        )
        assert display._agents["r1"]["tokens"] == 5000
        assert display._agents["r1"]["tool_calls"] == 3

    def test_agent_completed_marks_done(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="r", task_id="r1", tokens=10000),
        )
        assert display._agents["r1"]["status"] == "done"
        assert display._agents["r1"]["tokens"] == 10000

    def test_agents_clear_on_new_phase(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.PHASE_COMPLETED,
            PhaseCompletedPayload(phase="file_review", workflow="test"),
        )
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="triage", workflow="test"),
        )
        assert len(display._agents) == 0


class TestWorkflowDisplayCumulativeTokens:
    def test_tracks_cumulative_tokens(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="a", task_id="a1", tokens=5000),
        )
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="b", task_id="b1", tokens=3000),
        )
        assert display._cumulative_tokens == 8000


class TestWorkflowDisplayMechanical:
    def test_mechanical_tool_tracking(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool="ruff", files_count=10),
        )
        assert display._current_tool == "ruff"
        emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(tool="ruff", findings_count=3, duration_ms=150),
        )
        assert display._current_tool is None
        assert len(display._mechanical_tools) == 1


class TestWorkflowDisplayRender:
    def test_render_produces_output(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        rendered = display._render()
        assert rendered is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_display.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.workflows.display'`

- [ ] **Step 3: Implement `WorkflowDisplay`**

```python
# codemonkeys/workflows/display.py
"""Unified CLI display for workflow execution.

Subscribes to workflow events and renders a single Rich Live display with:
- Phase checklist (pending/running/done)
- Per-agent cards within the active phase
- Mechanical tool results
- Fix progress
- Cumulative token total
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    TriageReadyPayload,
    WorkflowErrorPayload,
)
from codemonkeys.workflows.phases import Workflow

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class WorkflowDisplay:
    def __init__(
        self,
        workflow: Workflow,
        emitter: EventEmitter,
        console: Console | None = None,
    ) -> None:
        self._console = console or Console(stderr=True)
        self._phases = [p.name for p in workflow.phases]
        self._phase_status: dict[str, str] = {p: "pending" for p in self._phases}
        self._agents: dict[str, dict[str, Any]] = {}
        self._mechanical_tools: list[dict[str, Any]] = []
        self._current_tool: str | None = None
        self._fix_files: list[dict[str, str]] = []
        self._triage_info: str = ""
        self._error: str | None = None
        self._cumulative_tokens: int = 0
        self._live: Live | None = None
        self._tick: int = 0

        emitter.on(EventType.PHASE_STARTED, self._on_phase_started)
        emitter.on(EventType.PHASE_COMPLETED, self._on_phase_completed)
        emitter.on(EventType.AGENT_STARTED, self._on_agent_started)
        emitter.on(EventType.AGENT_PROGRESS, self._on_agent_progress)
        emitter.on(EventType.AGENT_COMPLETED, self._on_agent_completed)
        emitter.on(EventType.MECHANICAL_TOOL_STARTED, self._on_tool_started)
        emitter.on(EventType.MECHANICAL_TOOL_COMPLETED, self._on_tool_completed)
        emitter.on(EventType.TRIAGE_READY, self._on_triage_ready)
        emitter.on(EventType.FIX_PROGRESS, self._on_fix_progress)
        emitter.on(EventType.WORKFLOW_COMPLETED, self._on_completed)
        emitter.on(EventType.WORKFLOW_ERROR, self._on_error)

    def start(self) -> None:
        self._live = Live(
            self._render(), console=self._console, refresh_per_second=4
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def pause(self) -> None:
        if self._live:
            self._live.stop()

    def resume(self) -> None:
        if self._live:
            self._live.start()
        else:
            self.start()

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _spinner(self) -> str:
        self._tick += 1
        return _SPINNER_FRAMES[self._tick % len(_SPINNER_FRAMES)]

    def _render(self) -> Group:
        parts: list[Text | Table] = []

        # Header with cumulative tokens
        if self._cumulative_tokens > 0:
            header = Text(
                f"  [{self._cumulative_tokens:,} tokens total]", style="dim"
            )
            parts.append(header)

        # Phase checklist
        for name in self._phases:
            status = self._phase_status[name]
            line = Text()
            if status == "done":
                line.append("  ✓ ", style="green")
                line.append(name.replace("_", " "), style="green")
            elif status == "running":
                line.append(f"  {self._spinner()} ", style="yellow")
                line.append(name.replace("_", " "), style="bold yellow")
            else:
                line.append("  ○ ", style="dim")
                line.append(name.replace("_", " "), style="dim")
            parts.append(line)

            # Mechanical tool details
            if name == "mechanical_audit" and status == "running" and self._current_tool:
                tool_line = Text()
                tool_line.append(
                    f"      {self._spinner()} {self._current_tool}...", style="dim"
                )
                parts.append(tool_line)

            if name == "mechanical_audit" and self._mechanical_tools:
                for tool_info in self._mechanical_tools:
                    tool_line = Text()
                    tool_line.append(
                        f"      ✓ {tool_info['tool']}", style="dim green"
                    )
                    tool_line.append(
                        f"  {tool_info['findings']} finding"
                        f"{'s' if tool_info['findings'] != 1 else ''}",
                        style="dim",
                    )
                    tool_line.append(f"  {tool_info['duration_ms']}ms", style="dim")
                    parts.append(tool_line)

            # Agent cards within active phase
            if status == "running" and self._agents:
                table = Table(
                    show_header=True, expand=True, padding=(0, 1), box=None
                )
                table.add_column("Agent", style="bold cyan", no_wrap=True)
                table.add_column("Model", width=8, style="dim")
                table.add_column("Status", width=8)
                table.add_column("Activity", style="dim")
                table.add_column("Tokens", justify="right", width=10)
                table.add_column("Tools", justify="right", width=5)

                for info in self._agents.values():
                    status_text = (
                        Text("running", style="yellow")
                        if info["status"] == "running"
                        else Text("done", style="green")
                    )
                    table.add_row(
                        info["name"],
                        info.get("model", ""),
                        status_text,
                        info.get("current_tool", "")[:50],
                        f"{info.get('tokens', 0):,}",
                        str(info.get("tool_calls", 0)),
                    )
                parts.append(table)

            # Triage info
            if name == "triage" and self._triage_info:
                info_line = Text()
                info_line.append(f"      {self._triage_info}", style="dim")
                parts.append(info_line)

            # Fix progress
            if name == "fix" and self._fix_files:
                for fix_info in self._fix_files:
                    fix_line = Text()
                    if fix_info["status"] == "started":
                        fix_line.append(
                            f"      {self._spinner()} {fix_info['file']}",
                            style="yellow",
                        )
                    elif fix_info["status"] == "completed":
                        fix_line.append(
                            f"      ✓ {fix_info['file']}", style="green"
                        )
                    else:
                        fix_line.append(
                            f"      ✗ {fix_info['file']}", style="red"
                        )
                    parts.append(fix_line)

        if self._error:
            err_line = Text()
            err_line.append(f"\n  Error: {self._error}", style="bold red")
            parts.append(err_line)

        return Group(*parts)

    # -- Event handlers --

    def _on_phase_started(self, _: EventType, payload: BaseModel) -> None:
        p: PhaseStartedPayload = payload  # type: ignore[assignment]
        self._agents.clear()
        self._phase_status[p.phase] = "running"
        self._refresh()

    def _on_phase_completed(self, _: EventType, payload: BaseModel) -> None:
        p: PhaseCompletedPayload = payload  # type: ignore[assignment]
        self._phase_status[p.phase] = "done"
        self._current_tool = None
        self._refresh()

    def _on_agent_started(self, _: EventType, payload: BaseModel) -> None:
        p: AgentStartedPayload = payload  # type: ignore[assignment]
        self._agents[p.task_id] = {
            "name": p.agent_name,
            "model": p.model,
            "files_label": p.files_label,
            "status": "running",
            "current_tool": "",
            "tokens": 0,
            "tool_calls": 0,
        }
        self._refresh()

    def _on_agent_progress(self, _: EventType, payload: BaseModel) -> None:
        p: AgentProgressPayload = payload  # type: ignore[assignment]
        if p.task_id in self._agents:
            self._agents[p.task_id]["tokens"] = p.tokens
            self._agents[p.task_id]["tool_calls"] = p.tool_calls
            self._agents[p.task_id]["current_tool"] = p.current_tool
        self._refresh()

    def _on_agent_completed(self, _: EventType, payload: BaseModel) -> None:
        p: AgentCompletedPayload = payload  # type: ignore[assignment]
        if p.task_id in self._agents:
            self._agents[p.task_id]["status"] = "done"
            self._agents[p.task_id]["tokens"] = p.tokens
        self._cumulative_tokens += p.tokens
        self._refresh()

    def _on_tool_started(self, _: EventType, payload: BaseModel) -> None:
        p: MechanicalToolStartedPayload = payload  # type: ignore[assignment]
        self._current_tool = p.tool
        self._refresh()

    def _on_tool_completed(self, _: EventType, payload: BaseModel) -> None:
        p: MechanicalToolCompletedPayload = payload  # type: ignore[assignment]
        self._current_tool = None
        self._mechanical_tools.append(
            {"tool": p.tool, "findings": p.findings_count, "duration_ms": p.duration_ms}
        )
        self._refresh()

    def _on_triage_ready(self, _: EventType, payload: BaseModel) -> None:
        p: TriageReadyPayload = payload  # type: ignore[assignment]
        self._triage_info = f"{p.findings_count} findings, {p.fixable_count} fixable"
        self._refresh()

    def _on_fix_progress(self, _: EventType, payload: BaseModel) -> None:
        p: FixProgressPayload = payload  # type: ignore[assignment]
        for item in self._fix_files:
            if item["file"] == p.file:
                item["status"] = p.status
                self._refresh()
                return
        self._fix_files.append({"file": p.file, "status": p.status})
        self._refresh()

    def _on_completed(self, _: EventType, payload: BaseModel) -> None:
        self._refresh()
        self.stop()

    def _on_error(self, _: EventType, payload: BaseModel) -> None:
        p: WorkflowErrorPayload = payload  # type: ignore[assignment]
        self._error = p.error
        self._refresh()
        self.stop()
```

- [ ] **Step 4: Run display tests**

Run: `uv run pytest tests/test_display.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/display.py tests/test_display.py
git commit -m "feat: build unified WorkflowDisplay with phase checklist and agent cards"
```

---

### Task 7: Reorder gate future in engine

**Files:**
- Modify: `codemonkeys/workflows/engine.py:44-52`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py`:

```python
class TestGateFutureOrder:
    @pytest.mark.asyncio
    async def test_gate_future_exists_when_waiting_event_fires(self) -> None:
        """The gate future must be created before WAITING_FOR_USER is emitted,
        so event handlers can call resolve_gate() synchronously."""

        future_existed: list[bool] = []

        async def gate_phase(ctx: WorkflowContext) -> dict[str, str]:
            return {"input": ctx.user_input}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="gate", phase_type=PhaseType.GATE, execute=gate_phase),
            ],
        )

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)

        def on_waiting(_: EventType, payload: object) -> None:
            future_existed.append(engine._gate_future is not None)
            engine.resolve_gate("user_says_go")

        emitter.on(EventType.WAITING_FOR_USER, on_waiting)

        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        await engine.run(workflow, ctx)

        assert future_existed == [True]
        assert ctx.phase_results["gate"] == {"input": "user_says_go"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine.py::TestGateFutureOrder -v`
Expected: FAIL — `future_existed == [False]` because the future is created after the emit

- [ ] **Step 3: Reorder the lines in `engine.py`**

In `codemonkeys/workflows/engine.py`, change the gate handling block from:

```python
if phase.phase_type == PhaseType.GATE:
    self._emitter.emit(
        EventType.WAITING_FOR_USER,
        WaitingForUserPayload(phase=phase.name, workflow=workflow.name),
    )
    loop = asyncio.get_running_loop()
    self._gate_future = loop.create_future()
    context.user_input = await self._gate_future
    self._gate_future = None
```

To:

```python
if phase.phase_type == PhaseType.GATE:
    loop = asyncio.get_running_loop()
    self._gate_future = loop.create_future()
    self._emitter.emit(
        EventType.WAITING_FOR_USER,
        WaitingForUserPayload(phase=phase.name, workflow=workflow.name),
    )
    context.user_input = await self._gate_future
    self._gate_future = None
```

- [ ] **Step 4: Run all engine tests**

Run: `uv run pytest tests/test_engine.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/engine.py tests/test_engine.py
git commit -m "fix: create gate future before emitting WAITING_FOR_USER"
```

---

### Task 8: Rewrite `run_review.py` as thin CLI wrapper

**Files:**
- Rewrite: `codemonkeys/run_review.py`
- Modify: `pyproject.toml` (entry point)

- [ ] **Step 1: Rewrite `run_review.py`**

```python
# codemonkeys/run_review.py
"""CLI review pipeline — thin wrapper over the workflow engine.

Run from the project root:
    uv run python -m codemonkeys.run_review --diff
    uv run python -m codemonkeys.run_review --files codemonkeys/core/runner.py
    uv run python -m codemonkeys.run_review --auto-fix
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from codemonkeys.core.sandbox import restrict
from codemonkeys.workflows.compositions import (
    ReviewConfig,
    make_diff_workflow,
    make_files_workflow,
    make_full_repo_workflow,
    make_post_feature_workflow,
)
from codemonkeys.workflows.display import WorkflowDisplay
from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType, WaitingForUserPayload
from codemonkeys.workflows.phases import WorkflowContext

console = Console()


def _init_log_dir(cwd: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = cwd / ".codemonkeys" / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _select_mode() -> str:
    console.print(
        Panel(
            "[bold]Select review scope[/bold]\n\n"
            "  [bold]1[/bold]  git diff — changed files vs HEAD\n"
            "  [bold]2[/bold]  full repo — all .py files\n",
            border_style="blue",
            padding=(1, 2),
        )
    )
    choice = console.input("  [bold]>[/bold] ").strip()
    if choice == "2":
        return "repo"
    return "diff"


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.files:
        return "files"
    if args.diff:
        return "diff"
    if args.repo:
        return "repo"
    return _select_mode()


def _pick_workflow(config: ReviewConfig):
    if config.mode == "files":
        return make_files_workflow(auto_fix=config.auto_fix)
    if config.mode == "diff":
        return make_diff_workflow(auto_fix=config.auto_fix)
    if config.mode == "post_feature":
        return make_post_feature_workflow(auto_fix=config.auto_fix)
    return make_full_repo_workflow(auto_fix=config.auto_fix)


def _handle_triage_gate(
    engine: WorkflowEngine, display: WorkflowDisplay
) -> None:
    display.pause()
    console.print(
        Panel(
            "[bold]Enter what you want to fix[/bold] (natural language)\n\n"
            '  [dim]"fix everything"[/dim]\n'
            '  [dim]"fix the high severity ones"[/dim]\n'
            '  [dim]"fix all except style issues"[/dim]\n'
            '  [dim]"just fix #2 and #5"[/dim]\n'
            '  [dim]"skip" to skip fixes[/dim]',
            border_style="blue",
            padding=(1, 2),
        )
    )
    user_input = console.input("  [bold]>[/bold] ").strip()
    display.resume()

    if not user_input or user_input.lower() == "skip":
        engine.resolve_gate([])
    else:
        engine.resolve_gate(user_input)


async def main_async(args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    restrict(cwd)
    log_dir = _init_log_dir(cwd)

    mode = _resolve_mode(args)
    config = ReviewConfig(
        mode=mode,
        target_files=args.files,
        auto_fix=args.auto_fix,
        graph=getattr(args, "graph", False),
    )

    emitter = EventEmitter()
    workflow = _pick_workflow(config)
    display = WorkflowDisplay(workflow, emitter)
    engine = WorkflowEngine(emitter)

    def on_waiting(_: EventType, payload: object) -> None:
        _handle_triage_gate(engine, display)

    emitter.on(EventType.WAITING_FOR_USER, on_waiting)

    ctx = WorkflowContext(
        cwd=str(cwd),
        run_id=str(log_dir.relative_to(cwd / ".codemonkeys")),
        config=config,
        log_dir=log_dir,
    )

    console.print(
        Panel(
            f"[dim]Logs:[/dim] {log_dir}",
            title="[bold]codemonkeys review[/bold]",
            border_style="bright_blue",
        )
    )

    display.start()
    try:
        await engine.run(workflow, ctx)
    finally:
        display.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="codemonkeys review pipeline")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--files", nargs="+", help="Specific files to review")
    scope.add_argument(
        "--diff", action="store_true", help="Review changed files (git diff vs HEAD)"
    )
    scope.add_argument(
        "--repo", action="store_true", help="Review all .py files in the repo"
    )
    parser.add_argument(
        "--auto-fix", action="store_true", help="Fix all findings without triage"
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Generate an interactive HTML workflow graph after run",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update `pyproject.toml` entry point**

Change the entry point from the TUI to the review CLI:

```toml
[project.scripts]
codemonkeys = "codemonkeys.run_review:main"
```

- [ ] **Step 3: Run lint and type check**

Run: `uv run ruff check codemonkeys/run_review.py && uv run ruff format codemonkeys/run_review.py`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add codemonkeys/run_review.py pyproject.toml
git commit -m "refactor: rewrite run_review.py as thin CLI wrapper over workflow engine"
```

---

### Task 9: Fix `implement.py` imports

**Files:**
- Modify: `codemonkeys/workflows/implement.py:62-68`
- Test: `tests/test_implement_workflow.py`

- [ ] **Step 1: Update imports in `implement.py`**

Replace the import block in `_auto_review`:

```python
# Old:
from codemonkeys.workflows.review import (
    _architecture,
    _discover,
    _fix,
    _review,
    _triage,
)

# New:
from codemonkeys.workflows.phase_library import (
    architecture_review,
    discover_diff,
    file_review,
    fix,
    triage,
)
```

And update the `_auto_review` function body to use the phase library functions. These take `WorkflowContext` and return dicts, same as the old ones:

```python
async def _auto_review(ctx: WorkflowContext) -> dict[str, Any]:
    from codemonkeys.workflows.phase_library import (
        architecture_review,
        file_review,
        fix,
        triage,
    )
    from codemonkeys.workflows.phase_library.discovery import discover_diff
    from codemonkeys.workflows.compositions import ReviewConfig

    review_ctx = WorkflowContext(
        cwd=ctx.cwd,
        run_id=ctx.run_id,
        config=ReviewConfig(mode="diff", auto_fix=True),
        emitter=ctx.emitter,
        log_dir=ctx.log_dir,
        phase_results={},
    )

    discover_result = await discover_diff(review_ctx)
    review_ctx.phase_results["discover"] = discover_result

    review_result = await file_review(review_ctx)
    review_ctx.phase_results["file_review"] = review_result

    arch_result = await architecture_review(review_ctx)
    review_ctx.phase_results["architecture_review"] = arch_result

    triage_result = await triage(review_ctx)
    review_ctx.phase_results["triage"] = triage_result

    if triage_result["fix_requests"]:
        fix_result = await fix(review_ctx)
        return {
            "findings": review_result.get("file_findings", []),
            "architecture_findings": arch_result.get("architecture_findings"),
            "fix_results": fix_result.get("fix_results", []),
        }

    return {
        "findings": review_result.get("file_findings", []),
        "architecture_findings": arch_result.get("architecture_findings"),
        "fix_results": [],
    }
```

- [ ] **Step 2: Run implement workflow tests**

Run: `uv run pytest tests/test_implement_workflow.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add codemonkeys/workflows/implement.py
git commit -m "refactor: update implement workflow to use phase_library instead of workflows/review"
```

---

### Task 10: Delete dead code

**Files:**
- Delete: `codemonkeys/tui/` (entire directory)
- Delete: `codemonkeys/cli.py`
- Delete: `codemonkeys/workflows/progress.py`
- Delete: `codemonkeys/workflows/review.py`
- Delete: `tests/test_tui_app.py`
- Delete: `tests/test_tui_analyzer.py`
- Delete: `tests/test_tui_dashboard.py`
- Delete: `tests/test_tui_queue.py`
- Delete: `tests/test_cli.py`
- Delete: `tests/test_progress.py`
- Delete: `tests/test_review_workflow.py`

- [ ] **Step 1: Delete TUI files**

```bash
rm -rf codemonkeys/tui/
rm codemonkeys/cli.py
```

- [ ] **Step 2: Delete duplicate workflow files**

```bash
rm codemonkeys/workflows/progress.py
rm codemonkeys/workflows/review.py
```

- [ ] **Step 3: Delete corresponding tests**

```bash
rm tests/test_tui_app.py tests/test_tui_analyzer.py tests/test_tui_dashboard.py tests/test_tui_queue.py
rm tests/test_cli.py
rm tests/test_progress.py
rm tests/test_review_workflow.py
```

- [ ] **Step 4: Run full test suite to confirm nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: all remaining tests PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check --fix . && uv run ruff format .`
Run: `uv run pyright .`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: delete TUI, duplicate workflows/review.py, and WorkflowProgress"
```

---

### Task 11: Final integration verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS

- [ ] **Step 2: Run lint and type check**

Run: `uv run ruff check . && uv run pyright .`
Expected: clean

- [ ] **Step 3: Verify the CLI runs**

Run: `uv run python -m codemonkeys.run_review --help`
Expected: shows help with `--files`, `--diff`, `--repo`, `--auto-fix`, `--graph` options

- [ ] **Step 4: Verify imports are clean**

Run: `python -c "from codemonkeys.core.runner import AgentRunner; from codemonkeys.core.run_result import RunResult; from codemonkeys.workflows.display import WorkflowDisplay; print('OK')"`
Expected: prints `OK`

- [ ] **Step 5: Commit any final fixes**

If any issues found in steps 1-4, fix and commit.
