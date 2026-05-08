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
        suffix = f", path={path}" if path else ""
        return f"Grep('{pattern}'{suffix})"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:100]})"
    return f"{tool_name}({json.dumps(tool_input, default=str)[:200]})"


def format_tool_result(data: dict, *, verbose: bool = False) -> str:
    """Extract a readable summary from a raw SDK tool result.

    verbose=False (default): short hint for stdout (e.g. "app.py (42 lines, 1234 chars)")
    verbose=True: includes truncated content for audit traces
    """
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
        content_len = len(content) if isinstance(content, str) else 0
        if not verbose:
            return f"{path} ({num_lines} lines, {content_len} chars)"
        if isinstance(content, str) and len(content) > READ_CONTENT_CAP:
            content = (
                content[:READ_CONTENT_CAP]
                + "\n... (truncated FOR THIS AUDIT TRACE ONLY — "
                + f"the reviewer saw the full {content_len} chars, {num_lines} lines)"
            )
        return f"{path} ({num_lines} lines):\n{content}"
    parts = []
    if "numFiles" in tur:
        parts.append(f"{tur['numFiles']} files")
    if "numLines" in tur:
        parts.append(f"{tur['numLines']} lines")
    if parts:
        return ", ".join(parts)
    result = str(tur)[:RESULT_CAP]
    return result if result not in ("{}", "[]", "") else ""


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
            summary = format_tool_result(event.data, verbose=True)
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
