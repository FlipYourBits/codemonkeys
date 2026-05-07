"""Internal helpers for AgentRunner: pricing estimation, tool detail, message serialisation."""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    RateLimitEvent,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    ToolUseBlock,
)

from claude_agent_sdk.types import HookEvent


_PRICING: dict[str, dict[str, float]] = {
    "opus": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "haiku": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
}


def _estimate_cost(usage: dict[str, Any], model: str) -> float:
    rates = _PRICING.get(model, _PRICING["sonnet"])
    m = 1_000_000
    return (
        usage.get("input_tokens", 0) * rates["input"] / m
        + usage.get("output_tokens", 0) * rates["output"] / m
        + usage.get("cache_read_input_tokens", 0) * rates["cache_read"] / m
        + usage.get("cache_creation_input_tokens", 0) * rates["cache_creation"] / m
    )


OnDenyCallback = Any  # (command: str, patterns: list[str]) -> None


def _build_tool_hooks(
    allowed_tools: list[str],
    on_deny: OnDenyCallback | None = None,
) -> dict[HookEvent, list[HookMatcher]] | None:
    """Build PreToolUse hooks that hard-enforce Bash command patterns.

    Parses patterns like "Bash(git ls-files*)" from allowed_tools.
    Returns a hooks dict for ClaudeAgentOptions, or None if no Bash
    patterns need enforcement.
    """
    bash_patterns: list[str] = []

    for spec in allowed_tools:
        m = re.match(r"^Bash\((.+)\)$", spec)
        if m:
            bash_patterns.append(m.group(1))

    if not bash_patterns:
        return None

    async def _enforce_bash(
        hook_input: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookJSONOutput:
        tool_input = hook_input.get("tool_input", {})  # type: ignore[union-attr]
        command = tool_input.get("command", "").strip()
        for pattern in bash_patterns:
            if fnmatch.fnmatch(command, pattern):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }
        if on_deny:
            on_deny(command, bash_patterns)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Bash command not allowed. Permitted: {bash_patterns}"
                ),
            }
        }

    hooks: dict[HookEvent, list[HookMatcher]] = {
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[_enforce_bash])]
    }
    return hooks


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
        raw_structured = getattr(message, "structured_output", None)
        if raw_structured is not None:
            if isinstance(raw_structured, str):
                entry["structured_output"] = raw_structured[:2000]
            else:
                entry["structured_output"] = raw_structured
        entry["usage"] = message.usage
        entry["cost"] = getattr(message, "total_cost_usd", None)
        entry["duration_ms"] = getattr(message, "duration_ms", 0)
    elif isinstance(message, TaskStartedMessage):
        entry["task_id"] = message.task_id
        entry["description"] = message.description
    elif isinstance(message, TaskProgressMessage):
        usage = message.usage
        entry["task_id"] = message.task_id
        entry["usage"] = (
            dict(usage)
            if isinstance(usage, dict)
            else {
                "total_tokens": getattr(usage, "total_tokens", 0),
                "tool_uses": getattr(usage, "tool_uses", 0),
            }
        )
    elif isinstance(message, TaskNotificationMessage):
        entry["task_id"] = message.task_id
        usage = message.usage
        if usage:
            entry["usage"] = (
                dict(usage)
                if isinstance(usage, dict)
                else {
                    "total_tokens": getattr(usage, "total_tokens", 0),
                }
            )
    elif isinstance(message, RateLimitEvent):
        info = message.rate_limit_info
        entry["status"] = info.status
        entry["rate_limit_type"] = info.rate_limit_type
        entry["resets_at"] = info.resets_at
        entry["utilization"] = info.utilization
    return entry
