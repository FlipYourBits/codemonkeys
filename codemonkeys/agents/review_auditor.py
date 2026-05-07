"""Review auditor agent — verifies reviewer behavior against its mandate."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from codemonkeys.core.events import (
    Event,
    RawMessage,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
)
from codemonkeys.core.types import AgentDefinition, RunResult

THINKING_CAP = 3000
READ_CONTENT_CAP = 1000
RESULT_CAP = 500

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


def _format_tool_input(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Read":
        return tool_input.get("file_path", "?")
    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "?")
        path = tool_input.get("path", "")
        return f"'{pattern}'" + (f", path={path}" if path else "")
    if tool_name in ("Edit", "Write"):
        return tool_input.get("file_path", "?")
    if tool_name == "Bash":
        return f"$ {tool_input.get('command', '')[:100]}"
    return json.dumps(tool_input, default=str)[:200]


def _extract_tool_result(data: dict) -> str:
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


def _format_event_trace(events: list[Event]) -> str:
    if not events:
        return "(empty trace)"

    start_time = events[0].timestamp
    lines: list[str] = []

    for event in events:
        elapsed = event.timestamp - start_time
        ts = f"[{elapsed:5.1f}s]"

        if isinstance(event, ToolCall):
            inp = _format_tool_input(event.tool_name, event.tool_input)
            lines.append(f"{ts} TOOL: {event.tool_name}({inp})")

        elif isinstance(event, RawMessage) and event.message_type == "UserMessage":
            summary = _extract_tool_result(event.data)
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


def make_review_auditor(
    result: RunResult,
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Audits a reviewer agent's work to verify behavior compliance."""
    agent_def = result.agent_def
    if agent_def is None:
        raise ValueError("RunResult has no agent_def — cannot audit")

    findings_json = "null"
    if result.output is not None:
        findings_json = result.output.model_dump_json(indent=2)

    trace = _format_event_trace(result.events)
    tools_str = ", ".join(agent_def.tools) if agent_def.tools else "(none)"

    return AgentDefinition(
        name=f"auditor:{agent_def.name}",
        model=model,
        system_prompt=f"""\
You are a review auditor. Analyze the trace below and produce an audit verdict in one pass.

IMPORTANT: The event trace below may show truncated file contents and thinking text.
This truncation is ONLY in this audit view — the reviewer saw the full content.
Do NOT flag truncation as a coverage or hallucination issue.

## Reviewer Configuration

- **Agent:** {agent_def.name}
- **Model:** {agent_def.model}
- **Allowed tools:** {tools_str}

### Reviewer's System Prompt

{agent_def.system_prompt}

## Event Trace

{trace}

## Structured Output (Findings)

{findings_json}

## Checks

1. **file_coverage** — Did it Read every assigned file?
2. **tool_compliance** — Only used {tools_str}? Any denied calls?
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
