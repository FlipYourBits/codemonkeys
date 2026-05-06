# Agent Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agent that analyzes another agent's logs against its source code to verify it behaved correctly and efficiently.

**Architecture:** A pure-Python log metrics extractor parses JSONL logs into a structured summary. A sonnet-based auditor agent reads the original agent's `.py` source and the extracted metrics, then produces a pass/fail verdict with narrative analysis. Integrates into the CLI via `--audit` flag.

**Tech Stack:** Python 3.12, Pydantic, claude_agent_sdk, pytest

---

### Task 1: Audit Schema (`codemonkeys/artifacts/schemas/audit.py`)

**Files:**
- Create: `codemonkeys/artifacts/schemas/audit.py`
- Create: `tests/test_audit_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audit_schema.py
from __future__ import annotations

from codemonkeys.artifacts.schemas.audit import AgentAudit, Issue


class TestAuditSchema:
    def test_issue_round_trips(self):
        issue = Issue(
            category="unauthorized_tool",
            turn=3,
            description="Agent called Bash but only Read is allowed",
            evidence='{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}',
        )
        data = issue.model_dump()
        assert data["category"] == "unauthorized_tool"
        assert data["turn"] == 3
        rebuilt = Issue.model_validate(data)
        assert rebuilt == issue

    def test_issue_turn_is_optional(self):
        issue = Issue(
            category="off_task",
            turn=None,
            description="Agent reasoning went off-topic",
            evidence="Thinking block about unrelated file",
        )
        assert issue.turn is None

    def test_agent_audit_pass_verdict(self):
        audit = AgentAudit(
            agent_name="changelog_reviewer",
            verdict="pass",
            summary="Agent completed the review correctly and efficiently.",
            issues=[],
            token_assessment="Reasonable token usage for the task.",
            recommendations=[],
        )
        schema = AgentAudit.model_json_schema()
        assert "verdict" in schema["properties"]
        assert audit.verdict == "pass"

    def test_agent_audit_fail_with_issues(self):
        audit = AgentAudit(
            agent_name="readme_reviewer",
            verdict="fail",
            summary="Agent used unauthorized tools and went off-task.",
            issues=[
                Issue(
                    category="unauthorized_tool",
                    turn=5,
                    description="Called Write tool",
                    evidence="tool_use Write",
                ),
                Issue(
                    category="off_task",
                    turn=7,
                    description="Spent 3 turns analyzing pyproject.toml",
                    evidence="Thinking: let me check the build config...",
                ),
            ],
            token_assessment="Excessive — 40k tokens for a simple review.",
            recommendations=["Add explicit constraint: do not modify files"],
        )
        assert audit.verdict == "fail"
        assert len(audit.issues) == 2

    def test_category_literal_rejects_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            Issue(
                category="invalid_category",
                turn=1,
                description="test",
                evidence="test",
            )

    def test_verdict_literal_rejects_invalid(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            AgentAudit(
                agent_name="test",
                verdict="maybe",
                summary="test",
                issues=[],
                token_assessment="test",
                recommendations=[],
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audit_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.artifacts.schemas.audit'`

- [ ] **Step 3: Write implementation**

```python
# codemonkeys/artifacts/schemas/audit.py
"""Schemas for agent audit results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Issue(BaseModel):
    category: Literal[
        "unauthorized_tool",
        "inappropriate_tool_use",
        "repeated_tool_call",
        "wasted_turn",
        "off_task",
        "instruction_violation",
        "output_problem",
    ] = Field(description="Type of issue found in the agent's behavior")
    turn: int | None = Field(
        description="Which assistant turn the issue occurred on, or null if general"
    )
    description: str = Field(description="What happened")
    evidence: str = Field(
        description="Quote from thinking block, tool call, or output that demonstrates the issue"
    )


class AgentAudit(BaseModel):
    agent_name: str = Field(description="Name of the agent that was audited")
    verdict: Literal["pass", "fail"] = Field(
        description="pass if agent behaved correctly, fail if instruction violations or off-task behavior"
    )
    summary: str = Field(
        description="2-3 sentence narrative of what the agent did and how well it performed"
    )
    issues: list[Issue] = Field(
        default_factory=list,
        description="Specific issues found, empty if verdict is pass",
    )
    token_assessment: str = Field(
        description="Brief assessment of whether token usage was reasonable for the task"
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggestions for improving the agent's prompt or configuration",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_audit_schema.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/artifacts/schemas/audit.py tests/test_audit_schema.py
git commit -m "feat: add audit schema for agent auditor (Issue, AgentAudit)"
```

---

### Task 2: Log Metrics Extractor (`codemonkeys/core/log_metrics.py`)

**Files:**
- Create: `codemonkeys/core/log_metrics.py`
- Create: `tests/test_log_metrics.py`

The extractor parses JSONL log files (produced by `AgentRunner._write_log`) into a structured `LogMetrics` dataclass. It needs to handle the exact event format from `_runner_helpers._serialize_message`.

JSONL format reference (from actual logs):
- Line 1: `{"event": "agent_start", "name": "...", "model": "...", "tools": [...], "user_prompt": "...", "ts": "..."}`
- Middle lines: `{"type": "AssistantMessage"|"UserMessage"|"SystemMessage"|"RateLimitEvent", ...}`
- `AssistantMessage` has `usage` dict and `content` array of `{"type": "thinking"|"tool_use"|"text", ...}` blocks
- Last line: `{"type": "ResultMessage", "result": "...", "usage": {...}, "cost": 0.123, "duration_ms": 1234}`
- There is also a `{"event": "tool_denied", ...}` event type for denied Bash commands

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_log_metrics.py
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from codemonkeys.core.log_metrics import LogMetrics, ToolCall, Turn, extract_metrics


def _write_log(tmp_path: Path, lines: list[dict]) -> Path:
    """Write JSONL lines to a temp log file and a companion .md file."""
    log_file = tmp_path / "test_agent_2026-01-01_00-00-00.log"
    log_file.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    md_file = tmp_path / "test_agent_2026-01-01_00-00-00.md"
    md_file.write_text(
        "# Agent: test_agent\n\n**Model:** sonnet\n**Tools:** Read, Grep\n\n"
        "## System Prompt\n\n```\nYou review files.\n```\n\n"
        "## User Prompt\n\n```\nReview foo.py\n```\n\n"
        "## Structured Output\n\n```json\n{}\n```\n"
    )
    return log_file


MINIMAL_LOG = [
    {
        "event": "agent_start",
        "name": "test_agent",
        "model": "sonnet",
        "tools": ["Read", "Grep"],
        "prompt_length": 100,
        "user_prompt": "Review foo.py",
        "ts": "2026-01-01T00:00:00+00:00",
    },
    {
        "type": "SystemMessage",
        "ts": "2026-01-01T00:00:01+00:00",
    },
    {
        "type": "AssistantMessage",
        "usage": {
            "input_tokens": 500,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "content": [
            {"type": "thinking", "thinking": "Let me read the file."},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}},
        ],
        "ts": "2026-01-01T00:00:02+00:00",
    },
    {
        "type": "UserMessage",
        "ts": "2026-01-01T00:00:03+00:00",
    },
    {
        "type": "AssistantMessage",
        "usage": {
            "input_tokens": 800,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 400,
        },
        "content": [
            {"type": "thinking", "thinking": "The file looks good."},
            {"type": "text", "text": "Review complete."},
        ],
        "ts": "2026-01-01T00:00:04+00:00",
    },
    {
        "type": "ResultMessage",
        "result": "Review complete.",
        "usage": {"input_tokens": 1300, "output_tokens": 150},
        "cost": 0.01,
        "duration_ms": 4000,
        "ts": "2026-01-01T00:00:05+00:00",
    },
]


class TestExtractMetrics:
    def test_extracts_agent_metadata(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.agent_name == "test_agent"
        assert metrics.model == "sonnet"
        assert metrics.allowed_tools == ["Read", "Grep"]
        assert metrics.user_prompt == "Review foo.py"

    def test_extracts_system_prompt_from_md(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert "You review files." in metrics.system_prompt

    def test_counts_assistant_turns(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert len(assistant_turns) == 2

    def test_extracts_tool_calls(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert len(metrics.tool_calls) == 1
        assert metrics.tool_calls[0].name == "Read"
        assert "foo.py" in metrics.tool_calls[0].args_summary

    def test_extracts_thinking_content(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert "Let me read the file." in assistant_turns[0].thinking_content

    def test_extracts_token_usage(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.total_input_tokens == 1300
        assert metrics.total_output_tokens == 150

    def test_extracts_cache_tokens(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        # Second assistant turn has cache_read_input_tokens=400
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert assistant_turns[1].cache_read_tokens == 400

    def test_extracts_cost_and_duration(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.total_cost == 0.01
        assert metrics.duration_ms == 4000

    def test_extracts_structured_output(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.structured_output == "Review complete."


class TestRepeatedToolCalls:
    def test_detects_repeated_tool_calls(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],  # agent_start
            MINIMAL_LOG[1],  # SystemMessage
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}},
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 200, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}},
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],  # ResultMessage
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.repeated_tool_calls) >= 1
        assert metrics.repeated_tool_calls[0].name == "Read"

    def test_no_false_positives_for_different_args(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}},
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 200, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "bar.py"}},
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.repeated_tool_calls) == 0


class TestUnauthorizedToolCalls:
    def test_detects_unauthorized_tool(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],  # allowed_tools: ["Read", "Grep"]
            MINIMAL_LOG[1],
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.unauthorized_tool_calls) == 1
        assert metrics.unauthorized_tool_calls[0].name == "Bash"

    def test_bash_pattern_matching(self, tmp_path):
        """Bash(git log*) should allow 'git log --oneline' but not 'ls'."""
        log_lines = [
            {
                "event": "agent_start",
                "name": "test_agent",
                "model": "haiku",
                "tools": ["Read", "Bash(git log*)"],
                "prompt_length": 100,
                "user_prompt": "Check history",
                "ts": "2026-01-01T00:00:00+00:00",
            },
            {"type": "SystemMessage", "ts": "2026-01-01T00:00:01+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "git log --oneline -5"}},
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        # "git log --oneline -5" matches "Bash(git log*)" — authorized
        # "ls -la" does not match any Bash pattern — unauthorized
        assert len(metrics.unauthorized_tool_calls) == 1
        assert "ls" in metrics.unauthorized_tool_calls[0].args_summary


class TestRateLimitEvents:
    def test_captures_rate_limit_events(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "RateLimitEvent",
                "status": "allowed",
                "rate_limit_type": "five_hour",
                "resets_at": 1778101800,
                "utilization": None,
                "ts": "2026-01-01T00:00:01+00:00",
            },
            MINIMAL_LOG[2],  # AssistantMessage
            MINIMAL_LOG[3],  # UserMessage
            MINIMAL_LOG[-1],  # ResultMessage
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.rate_limit_events) == 1
        assert metrics.rate_limit_events[0]["status"] == "allowed"


class TestToolDeniedEvents:
    def test_captures_tool_denied(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "event": "tool_denied",
                "tool": "Bash",
                "command": "rm -rf /",
                "permitted_patterns": ["git log*"],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.unauthorized_tool_calls) == 1
        assert "rm -rf" in metrics.unauthorized_tool_calls[0].args_summary


class TestSerialization:
    def test_to_json_roundtrips(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        json_str = metrics.to_json()
        data = json.loads(json_str)
        assert data["agent_name"] == "test_agent"
        assert isinstance(data["turns"], list)
        assert isinstance(data["tool_calls"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.core.log_metrics'`

- [ ] **Step 3: Write implementation**

```python
# codemonkeys/core/log_metrics.py
"""Extract structured metrics from agent JSONL log files."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ToolCall:
    turn: int
    name: str
    args_summary: str


@dataclass
class Turn:
    index: int
    role: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    text_content: str = ""


@dataclass
class LogMetrics:
    agent_name: str = ""
    model: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    total_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cost: float = 0.0
    duration_ms: int = 0
    turns: list[Turn] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    repeated_tool_calls: list[ToolCall] = field(default_factory=list)
    unauthorized_tool_calls: list[ToolCall] = field(default_factory=list)
    rate_limit_events: list[dict] = field(default_factory=list)
    structured_output: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


def _summarize_tool_args(name: str, tool_input: dict) -> str:
    if name in ("Read", "Edit", "Write"):
        return tool_input.get("file_path", "?")
    if name == "Grep":
        return tool_input.get("pattern", "?")
    if name == "Glob":
        return tool_input.get("pattern", tool_input.get("path", "?"))
    if name == "Bash":
        return tool_input.get("command", "")[:120]
    if name == "StructuredOutput":
        return "(structured output)"
    return str(tool_input)[:120]


def _is_tool_authorized(tool_name: str, tool_input: dict, allowed_tools: list[str]) -> bool:
    for spec in allowed_tools:
        if spec == tool_name:
            return True
        m = re.match(r"^(\w+)\((.+)\)$", spec)
        if m and m.group(1) == tool_name:
            pattern = m.group(2)
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                if fnmatch.fnmatch(command, pattern):
                    return True
    # StructuredOutput is always implicitly allowed (SDK internal)
    if tool_name == "StructuredOutput":
        return True
    return False


def _extract_system_prompt(log_file: Path) -> str:
    md_candidates = list(log_file.parent.glob(log_file.stem.rsplit(".", 1)[0] + "*.md"))
    if not md_candidates:
        md_candidates = list(log_file.parent.glob("*.md"))
    for md_path in md_candidates:
        text = md_path.read_text()
        marker = "## System Prompt\n\n```\n"
        start = text.find(marker)
        if start == -1:
            continue
        start += len(marker)
        end = text.find("\n```\n", start)
        if end == -1:
            continue
        return text[start:end]
    return ""


def extract_metrics(log_file: Path) -> LogMetrics:
    metrics = LogMetrics()
    assistant_turn_index = 0

    lines = log_file.read_text().strip().split("\n")
    for line in lines:
        entry = json.loads(line)

        if entry.get("event") == "agent_start":
            metrics.agent_name = entry.get("name", "")
            metrics.model = entry.get("model", "")
            metrics.allowed_tools = entry.get("tools", [])
            metrics.user_prompt = entry.get("user_prompt", "")
            continue

        if entry.get("event") == "tool_denied":
            tc = ToolCall(
                turn=assistant_turn_index,
                name=entry.get("tool", "Bash"),
                args_summary=entry.get("command", ""),
            )
            metrics.unauthorized_tool_calls.append(tc)
            metrics.tool_calls.append(tc)
            continue

        msg_type = entry.get("type", "")

        if msg_type == "RateLimitEvent":
            metrics.rate_limit_events.append({
                "status": entry.get("status"),
                "rate_limit_type": entry.get("rate_limit_type"),
                "resets_at": entry.get("resets_at"),
                "utilization": entry.get("utilization"),
            })
            continue

        if msg_type == "AssistantMessage":
            assistant_turn_index += 1
            usage = entry.get("usage", {})
            content_blocks = entry.get("content", [])

            thinking_parts = []
            text_parts = []
            turn_tool_calls = []

            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "thinking":
                    thinking_parts.append(block.get("thinking", ""))
                elif block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tc = ToolCall(
                        turn=assistant_turn_index,
                        name=tool_name,
                        args_summary=_summarize_tool_args(tool_name, tool_input),
                    )
                    turn_tool_calls.append(tc)
                    metrics.tool_calls.append(tc)

                    if not _is_tool_authorized(tool_name, tool_input, metrics.allowed_tools):
                        metrics.unauthorized_tool_calls.append(tc)

            turn = Turn(
                index=assistant_turn_index,
                role="assistant",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                thinking_content="\n".join(thinking_parts),
                tool_calls=turn_tool_calls,
                text_content="\n".join(text_parts),
            )
            metrics.turns.append(turn)
            metrics.total_turns = assistant_turn_index
            continue

        if msg_type == "ResultMessage":
            result_usage = entry.get("usage", {})
            metrics.total_input_tokens = result_usage.get("input_tokens", 0)
            metrics.total_output_tokens = result_usage.get("output_tokens", 0)
            metrics.total_cache_read_tokens = result_usage.get("cache_read_input_tokens", 0)
            metrics.total_cache_creation_tokens = result_usage.get(
                "cache_creation_input_tokens", 0
            )
            metrics.total_cost = entry.get("cost", 0.0) or 0.0
            metrics.duration_ms = entry.get("duration_ms", 0)
            metrics.structured_output = entry.get("result")
            continue

    metrics.system_prompt = _extract_system_prompt(log_file)

    # Detect repeated tool calls: same (name, args_summary) appearing more than once
    seen: dict[tuple[str, str], list[ToolCall]] = {}
    for tc in metrics.tool_calls:
        key = (tc.name, tc.args_summary)
        seen.setdefault(key, []).append(tc)
    for key, calls in seen.items():
        if len(calls) > 1:
            metrics.repeated_tool_calls.extend(calls)

    return metrics
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_log_metrics.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/log_metrics.py tests/test_log_metrics.py
git commit -m "feat: add log metrics extractor for JSONL agent logs"
```

---

### Task 3: Agent Auditor Factory (`codemonkeys/core/agents/agent_auditor.py`)

**Files:**
- Create: `codemonkeys/core/agents/agent_auditor.py`
- Create: `tests/test_agent_auditor.py`

This follows the same factory pattern as `changelog_reviewer.py` — a `make_agent_auditor()` function returning an `AgentDefinition`. The agent reads the target agent's `.py` source file to understand the contract, then analyzes `LogMetrics` JSON from the user prompt.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_auditor.py
from __future__ import annotations

from codemonkeys.core.agents.agent_auditor import make_agent_auditor, AGENT_SOURCES


class TestAgentAuditorFactory:
    def test_returns_agent_definition(self):
        agent = make_agent_auditor("codemonkeys/core/agents/changelog_reviewer.py")
        assert agent.description
        assert agent.model == "sonnet"
        assert "Read" in agent.tools
        assert agent.permissionMode == "dontAsk"

    def test_embeds_source_path_in_prompt(self):
        path = "codemonkeys/core/agents/readme_reviewer.py"
        agent = make_agent_auditor(path)
        assert path in agent.prompt

    def test_prompt_instructs_evaluation(self):
        agent = make_agent_auditor("codemonkeys/core/agents/changelog_reviewer.py")
        assert "instruction compliance" in agent.prompt.lower() or "instruction" in agent.prompt.lower()
        assert "tool" in agent.prompt.lower()
        assert "efficiency" in agent.prompt.lower() or "turn" in agent.prompt.lower()

    def test_agent_sources_registry_has_known_agents(self):
        assert "python_file_reviewer" in AGENT_SOURCES
        assert "changelog_reviewer" in AGENT_SOURCES
        assert "architecture_reviewer" in AGENT_SOURCES

    def test_agent_sources_paths_exist(self):
        from pathlib import Path
        for name, path in AGENT_SOURCES.items():
            assert Path(path).exists(), f"Agent source for {name} not found: {path}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_auditor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.core.agents.agent_auditor'`

- [ ] **Step 3: Write implementation**

```python
# codemonkeys/core/agents/agent_auditor.py
"""Agent auditor — analyzes another agent's logs against its source code.

Reads the target agent's .py file to extract the contract (prompt, tools,
output schema, guardrails), then compares against LogMetrics JSON to verify
the agent behaved correctly and efficiently.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

AGENT_SOURCES: dict[str, str] = {
    "python_file_reviewer": "codemonkeys/core/agents/python_file_reviewer.py",
    "architecture_reviewer": "codemonkeys/core/agents/architecture_reviewer.py",
    "changelog_reviewer": "codemonkeys/core/agents/changelog_reviewer.py",
    "readme_reviewer": "codemonkeys/core/agents/readme_reviewer.py",
    "python_code_fixer": "codemonkeys/core/agents/python_code_fixer.py",
    "python_implementer": "codemonkeys/core/agents/python_implementer.py",
    "python_characterization_tester": "codemonkeys/core/agents/python_characterization_tester.py",
    "python_structural_refactorer": "codemonkeys/core/agents/python_structural_refactorer.py",
    "spec_compliance_reviewer": "codemonkeys/core/agents/spec_compliance_reviewer.py",
}


def make_agent_auditor(agent_source_path: str) -> AgentDefinition:
    """Create an auditor agent that evaluates another agent's log against its source code."""
    return AgentDefinition(
        description=f"Audit agent behavior from logs vs source: {agent_source_path}",
        prompt=f"""\
You are an agent auditor. Your job is to analyze whether another agent
performed its task correctly and efficiently by comparing its source code
against its actual execution log.

## Step 1: Read the Agent Source

Read the agent source file at: {agent_source_path}

Extract from it:
- The agent's intended purpose (from the description and prompt text)
- The list of approved tools
- Any specific constraints or guardrails (e.g., "read-only", "do NOT modify files")
- The expected output format/schema
- Any method instructions (what steps the agent should follow)

## Step 2: Analyze the Log Metrics

The user prompt contains a JSON object with the full execution log metrics.
Analyze it for the following issues:

### Instruction Compliance
Did the agent follow its system prompt? Look for:
- Read-only agents that tried to write or modify files
- Agents that ignored specific constraints in their prompt
- Agents that skipped required steps from the method section
- Agents that produced output not matching the expected format

### Tool Discipline (Hard Violations)
The `unauthorized_tool_calls` field pre-flags tools not in the allowed list.
Confirm each one and explain the violation.

### Tool Discipline (Appropriateness)
Even for allowed tools, check whether each tool call was relevant to the
task. Look at the `tool_calls` list and the agent's `user_prompt` to judge:
- Did the agent read files unrelated to its task?
- Did the agent run commands outside the scope of its purpose?
- Were tool calls proportionate to the task complexity?

### Turn Efficiency
Look at the `turns` list and `repeated_tool_calls` for:
- Same file read more than once (the `repeated_tool_calls` field flags these)
- Redundant information gathering (grepping for something already found)
- Turns that produced no useful progress
- Excessive thinking without action

### Focus
Read the `thinking_content` in each turn. Flag:
- Extended reasoning about topics outside the agent's task
- Confusion about what to do next
- Tangential exploration of unrelated concerns

### Output Correctness
Compare the `structured_output` against the expected output schema from
the agent source. Check:
- Does it match the expected structure?
- Are fields populated with sensible values?
- Did the agent return findings about things it wasn't asked to review?

## Output Format

Return your findings as structured JSON matching the AgentAudit schema.

Verdict rules:
- "fail" if ANY issue has category: unauthorized_tool, instruction_violation,
  off_task, or output_problem
- "pass" if only efficiency issues (repeated_tool_call, wasted_turn,
  inappropriate_tool_use) — flag them in issues but pass the agent

Always include:
- A 2-3 sentence summary of what the agent did
- A token_assessment noting whether usage was reasonable
- Specific recommendations for prompt improvements if issues were found

## Guardrails

You are a **read-only auditor**. Do NOT modify any files. Only read the
agent source file specified above. Do not read any other files.""",
        model="sonnet",
        tools=["Read"],
        permissionMode="dontAsk",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_auditor.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/agents/agent_auditor.py tests/test_agent_auditor.py
git commit -m "feat: add agent auditor factory with source-vs-log analysis"
```

---

### Task 4: CLI Integration — `--audit` flag on `run_agent.py`

**Files:**
- Modify: `codemonkeys/run_agent.py`
- Modify: `tests/test_log_metrics.py` (add integration test)

Adds `--audit` flag to `run_agent.py`. When set, after the primary agent run completes, the auditor runs on that agent's logs.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_log_metrics.py`:

```python
class TestRunAgentAuditFlag:
    def test_audit_flag_is_accepted(self):
        """Verify the --audit flag is parsed without error."""
        import codemonkeys.run_agent as ra
        parser = ra._build_parser()
        args = parser.parse_args(["changelog_reviewer", "--audit"])
        assert args.audit is True

    def test_no_audit_by_default(self):
        import codemonkeys.run_agent as ra
        parser = ra._build_parser()
        args = parser.parse_args(["changelog_reviewer"])
        assert args.audit is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log_metrics.py::TestRunAgentAuditFlag -v`
Expected: FAIL — `AttributeError: module 'codemonkeys.run_agent' has no attribute '_build_parser'`

- [ ] **Step 3: Refactor argparse into `_build_parser()` and add `--audit` flag**

In `codemonkeys/run_agent.py`, extract the parser creation from `main()` into a `_build_parser()` function, add the `--audit` flag, add `"agent_auditor"` to `AGENT_NAMES`, add the auditor builder, and add the audit post-run logic.

Changes to `codemonkeys/run_agent.py`:

1. Add `"agent_auditor"` to `AGENT_NAMES` list.

2. Add the auditor builder function:

```python
def _build_agent_auditor(
    args: argparse.Namespace,
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.audit import AgentAudit
    from codemonkeys.core.agents.agent_auditor import make_agent_auditor

    source_path = args.agent_source
    if not source_path:
        console.print("[red]agent_auditor requires --agent-source[/red]")
        sys.exit(1)
    prompt_text = _read_prompt(args)
    if not prompt_text:
        console.print("[red]agent_auditor requires --prompt or --prompt-file with LogMetrics JSON[/red]")
        sys.exit(1)
    agent = make_agent_auditor(source_path)
    schema = {"type": "json_schema", "schema": AgentAudit.model_json_schema()}
    return agent, prompt_text, schema
```

3. Add it to the `builders` dict in `_build_agent()`:

```python
"agent_auditor": lambda: _build_agent_auditor(args),
```

4. Extract parser into `_build_parser()`:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single codemonkeys agent for testing and debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s python_file_reviewer --files codemonkeys/core/runner.py
  %(prog)s changelog_reviewer
  %(prog)s changelog_reviewer --audit""",
    )
    parser.add_argument("agent", choices=AGENT_NAMES, help="Agent to run")
    parser.add_argument("--files", nargs="+", help="Files to pass to the agent")
    parser.add_argument("--prompt", help="User prompt text")
    parser.add_argument("--prompt-file", help="Read user prompt from a file")
    parser.add_argument("--model", help="Override the agent's default model")
    parser.add_argument(
        "--resilience", action="store_true", help="(file_reviewer) Enable resilience checklist"
    )
    parser.add_argument(
        "--test-quality", action="store_true", help="(file_reviewer) Enable test quality checklist"
    )
    parser.add_argument(
        "--refactor-type",
        choices=["circular_deps", "layering", "god_modules", "extract_shared", "dead_code", "naming"],
        help="(structural_refactorer) Type of refactoring",
    )
    parser.add_argument(
        "--audit", action="store_true", help="Run the agent auditor on this agent's logs after completion"
    )
    parser.add_argument(
        "--agent-source", help="(agent_auditor) Path to the agent source .py file"
    )
    return parser
```

5. Update `main()` to use `_build_parser()`:

```python
def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))
```

6. Add audit post-run logic at the end of `main_async()`, after the primary result is printed:

```python
    if getattr(args, "audit", False) and args.agent != "agent_auditor":
        console.print("\n[bold]Running agent audit...[/bold]")
        from codemonkeys.artifacts.schemas.audit import AgentAudit
        from codemonkeys.core.agents.agent_auditor import AGENT_SOURCES, make_agent_auditor
        from codemonkeys.core.log_metrics import extract_metrics

        # Find the log file we just wrote
        log_files = sorted(log_dir.glob("*.log"))
        if log_files:
            metrics = extract_metrics(log_files[0])
            source_path = AGENT_SOURCES.get(name)
            if source_path:
                auditor = make_agent_auditor(source_path)
                audit_schema = {"type": "json_schema", "schema": AgentAudit.model_json_schema()}
                audit_result = await runner.run_agent(
                    auditor,
                    metrics.to_json(),
                    output_format=audit_schema,
                    agent_name="agent_auditor",
                )
                if audit_result.structured:
                    verdict = audit_result.structured.get("verdict", "?")
                    style = "green" if verdict == "pass" else "red"
                    console.print(Panel(
                        json.dumps(audit_result.structured, indent=2),
                        title=f"[{style}]Audit: {verdict.upper()}[/{style}]",
                        border_style=style,
                    ))
                else:
                    console.print("[yellow]Audit produced no structured output[/yellow]")
            else:
                console.print(f"[yellow]No source mapping for agent '{name}' — skipping audit[/yellow]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_log_metrics.py::TestRunAgentAuditFlag -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/run_agent.py tests/test_log_metrics.py
git commit -m "feat: add --audit flag to run_agent CLI for post-run agent auditing"
```

---

### Task 5: CLI Integration — `--audit` flag on `run_review.py`

**Files:**
- Modify: `codemonkeys/run_review.py`

Adds `--audit` flag to `run_review.py`. After the workflow completes, iterates over all log files in the run's log directory and dispatches the auditor on each.

- [ ] **Step 1: Add the `--audit` flag to the argparse group**

In `codemonkeys/run_review.py`, add after the `--graph` argument:

```python
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run the agent auditor on all agent logs after the workflow completes",
    )
```

- [ ] **Step 2: Pass `audit` through to `main_async` and add post-run logic**

At the end of `main_async()`, after `display.stop()` in the finally block, add:

```python
    if getattr(args, "audit", False):
        from codemonkeys.artifacts.schemas.audit import AgentAudit
        from codemonkeys.core.agents.agent_auditor import AGENT_SOURCES, make_agent_auditor
        from codemonkeys.core.log_metrics import extract_metrics

        log_files = sorted(log_dir.glob("*.log"))
        if not log_files:
            console.print("[yellow]No log files found for audit[/yellow]")
        else:
            console.print(f"\n[bold]Auditing {len(log_files)} agent run(s)...[/bold]\n")
            runner = AgentRunner(cwd=str(cwd), log_dir=log_dir)
            audit_schema = {"type": "json_schema", "schema": AgentAudit.model_json_schema()}
            for lf in log_files:
                metrics = extract_metrics(lf)
                agent_base = metrics.agent_name.split("__")[0]
                source_path = AGENT_SOURCES.get(agent_base)
                if not source_path:
                    console.print(f"  [dim]Skipping {metrics.agent_name} — no source mapping[/dim]")
                    continue
                auditor = make_agent_auditor(source_path)
                audit_result = await runner.run_agent(
                    auditor,
                    metrics.to_json(),
                    output_format=audit_schema,
                    agent_name=f"audit__{agent_base}",
                )
                if audit_result.structured:
                    verdict = audit_result.structured.get("verdict", "?")
                    style = "green" if verdict == "pass" else "red"
                    console.print(Panel(
                        json.dumps(audit_result.structured, indent=2),
                        title=f"[{style}]{agent_base}: {verdict.upper()}[/{style}]",
                        border_style=style,
                    ))
```

Note: `args` needs to be passed to `main_async`. Currently the signature is `async def main_async(args: argparse.Namespace)` and `args` is already available.

- [ ] **Step 3: Add import for AgentRunner at top of file**

The `AgentRunner` import is already not at the top level — it will be imported inside the audit block. No top-level import needed (keeps the lazy import pattern used for `make_deep_clean_workflow`).

- [ ] **Step 4: Manual test**

Run a quick review with audit:
```bash
uv run python -m codemonkeys.run_review --files codemonkeys/core/runner.py --audit
```

Verify:
- Normal review output appears first
- Audit results appear after with PASS/FAIL verdict
- Audit agent's own logs appear in the log directory (prefixed `audit__`)

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/run_review.py
git commit -m "feat: add --audit flag to run_review for post-workflow agent auditing"
```

---

### Task 6: Final Integration Test & Cleanup

**Files:**
- Modify: `tests/test_log_metrics.py` (add end-to-end extraction test on real logs)

- [ ] **Step 1: Add test that extracts metrics from actual log files if present**

```python
class TestRealLogExtraction:
    """Smoke test against actual log files if they exist."""

    def test_extract_from_real_log_if_available(self):
        log_dir = Path(".codemonkeys/logs")
        if not log_dir.exists():
            pytest.skip("No .codemonkeys/logs directory")
        log_files = sorted(log_dir.rglob("*.log"))
        if not log_files:
            pytest.skip("No log files found")

        metrics = extract_metrics(log_files[0])
        assert metrics.agent_name
        assert metrics.model
        assert metrics.total_turns > 0
        assert len(metrics.turns) > 0
        # Should have at least one tool call in a real run
        assert len(metrics.tool_calls) >= 0  # some agents might have zero
        # JSON serialization should work
        json_str = metrics.to_json()
        data = json.loads(json_str)
        assert data["agent_name"] == metrics.agent_name
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_log_metrics.py tests/test_audit_schema.py tests/test_agent_auditor.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run linting and type checking**

```bash
ruff check --fix . && ruff format .
pyright .
```

Fix any issues.

- [ ] **Step 4: Commit final cleanup**

```bash
git add -u
git commit -m "test: add real-log smoke test and lint fixes for agent auditor"
```
