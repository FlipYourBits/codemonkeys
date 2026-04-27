"""Per-node permission rules for Claude Agent SDK tool calls.

Rule syntax mirrors Claude Code's settings.local.json:

    "Bash"              -> matches every Bash invocation
    "Bash(python*)"     -> Bash where command matches fnmatch pattern "python*"
    "Bash(git push:*)"  -> Bash where command matches "git push:*"
    "Read"              -> every Read
    "Read(./src/**)"    -> Read where file_path matches "./src/**"
    "Edit(*.py)"        -> Edit where file_path matches "*.py"
    "Write"             -> every Write

Pattern matching uses fnmatch.fnmatchcase against the tool's primary input
field (command for Bash, file_path for Read/Edit/Write/Glob/Grep). Tools
without a known field can only be matched by name.
"""

from __future__ import annotations

import asyncio
import fnmatch
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

AskCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
UnmatchedPolicy = Literal["allow", "deny"] | AskCallback

_TOOL_INPUT_FIELDS: dict[str, str] = {
    "Bash": "command",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Glob": "pattern",
    "Grep": "pattern",
}


@dataclass(frozen=True)
class PermissionRule:
    tool: str
    pattern: str | None  # None = match any input

    @classmethod
    def parse(cls, rule: str) -> "PermissionRule":
        rule = rule.strip()
        if not rule:
            raise ValueError("empty permission rule")
        if "(" not in rule:
            return cls(tool=rule, pattern=None)
        if not rule.endswith(")"):
            raise ValueError(f"malformed rule (missing closing paren): {rule!r}")
        tool, _, rest = rule.partition("(")
        pattern = rest[:-1]  # strip trailing ")"
        return cls(tool=tool.strip(), pattern=pattern)

    def matches(self, tool_name: str, input_data: dict[str, Any]) -> bool:
        if self.tool != tool_name:
            return False
        if self.pattern is None:
            return True
        field = _TOOL_INPUT_FIELDS.get(tool_name)
        if field is None:
            return False
        value = input_data.get(field, "")
        if not isinstance(value, str):
            return False
        return fnmatch.fnmatchcase(value, self.pattern)


def _parse_rules(rules: list[str] | None) -> list[PermissionRule]:
    return [PermissionRule.parse(r) for r in (rules or [])]


def build_can_use_tool(
    *,
    allow: list[str] | None = None,
    deny: list[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
):
    """Return a `can_use_tool` callback for ClaudeAgentOptions.

    Deny rules win over allow rules. Unmatched tool calls fall through to
    `on_unmatched`: a string preset ("allow"/"deny") or an async callable
    that returns True/False.
    """
    allow_rules = _parse_rules(allow)
    deny_rules = _parse_rules(deny)

    async def can_use_tool(
        tool_name: str,
        input_data: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        for rule in deny_rules:
            if rule.matches(tool_name, input_data):
                return PermissionResultDeny(
                    message=f"denied by rule: {rule.tool}"
                    + (f"({rule.pattern})" if rule.pattern else "")
                )

        for rule in allow_rules:
            if rule.matches(tool_name, input_data):
                return PermissionResultAllow(updated_input=input_data)

        if on_unmatched == "allow":
            return PermissionResultAllow(updated_input=input_data)
        if on_unmatched == "deny":
            return PermissionResultDeny(
                message=f"no permission rule matched {tool_name}"
            )

        approved = await on_unmatched(tool_name, input_data)
        if approved:
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(message=f"user denied {tool_name}")

    return can_use_tool


async def ask_via_stdin(
    tool_name: str, input_data: dict[str, Any], prompt_fn: Any | None = None
) -> bool:
    """Prompt the user on stdin for an unmatched tool call.

    Returns True on 'y'/'yes' (case-insensitive). Returns False on any other
    input or when stdin is not a TTY (CI, pipes, headless runs).
    """
    if not sys.stdin.isatty():
        return False

    summary = ", ".join(f"{k}={v!r}" for k, v in list(input_data.items())[:3])
    text = f"[agentpipe] Allow {tool_name}({summary})? [y/N]:"
    if prompt_fn is not None:
        answer = await asyncio.to_thread(prompt_fn, text, None)
    else:
        answer = await asyncio.to_thread(input, f"\n{text} ")
    return answer.strip().lower() in ("y", "yes")
