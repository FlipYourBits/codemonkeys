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
    """Check if a tool call is permitted by the allowlist."""
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

    simple_tools = {t for t in allowed_tools if not _BASH_PATTERN_RE.match(t) and t != "Bash"}
    return tool_name in simple_tools


OnDenyCallback = Any  # (tool_name: str, command: str) -> None


def build_tool_hooks(
    allowed_tools: list[str],
    on_deny: OnDenyCallback | None = None,
) -> dict[HookEvent, list[HookMatcher]] | None:
    """Build PreToolUse hooks that enforce the tool allowlist.

    Returns None if no Bash pattern enforcement is needed.
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
