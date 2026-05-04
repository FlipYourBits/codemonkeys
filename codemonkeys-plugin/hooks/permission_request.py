"""PermissionRequest hook — auto-allow read-only operations."""
from __future__ import annotations

import json
import re
import sys

SAFE_TOOLS = {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}

SAFE_BASH_PATTERNS = [
    r"^ls\b",
    r"^pwd$",
    r"^which\b",
    r"^echo\b",
    r"^find\b",
    r"^wc\b",
    r"^head\b",
    r"^tail\b",
    r"^cat\b",
    r"^file\b",
    r"^stat\b",
    r"^du\b",
    r"^df\b",
    r"^git\s+(status|log|diff|branch|show|rev-parse|remote)\b",
    r"^npm\s+(list|ls|outdated)\b",
    r"^pip\s+(list|show|freeze)\b",
    r"^python\s+--version",
    r"^node\s+--version",
]


def main() -> None:
    data = json.loads(sys.stdin.read())
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in SAFE_TOOLS:
        _allow()
        return

    if tool_name == "Bash":
        command = tool_input.get("command", "").strip()
        for pattern in SAFE_BASH_PATTERNS:
            if re.match(pattern, command):
                _allow()
                return


def _allow() -> None:
    output = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    })
    print(output)


if __name__ == "__main__":
    main()
