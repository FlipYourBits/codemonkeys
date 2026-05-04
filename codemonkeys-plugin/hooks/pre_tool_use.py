"""PreToolUse hook — block destructive commands, .env access, opt-in write sandbox."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DESTRUCTIVE_PATTERNS = [
    (r"rm\s+.*-[rf]", "Use explicit file paths with rm instead of -rf flags"),
    (r"rm\s+--recursive", "Use explicit file paths with rm instead of --recursive"),
    (r"git\s+push\s+.*--force", "Use git push without --force"),
    (r"git\s+push\s+-f\b", "Use git push without -f"),
    (r"git\s+reset\s+--hard", "Use git reset --soft or git stash instead"),
    (r"git\s+clean\s+-[fdx]", "Use git clean -n (dry run) first"),
    (r"chmod\s+777", "Use more restrictive permissions (644 or 755)"),
]

ENV_SAFE_SUFFIXES = {".sample", ".example", ".template", ".test", ".ci"}


def main() -> None:
    data = json.loads(sys.stdin.read())
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = Path(data.get("cwd", ".")).resolve()

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern, suggestion in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                _deny(f"Blocked destructive command: `{pattern}`. {suggestion}.")
                return

    if _is_env_file_access(tool_name, tool_input):
        _deny("Blocked: .env file access. Use .env.sample or .env.example instead.")
        return

    if tool_name in ("Edit", "Write"):
        if not _sandbox_enabled(cwd):
            sys.exit(0)
        file_path = Path(tool_input.get("file_path", ""))
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(cwd)):
                _deny(f"Sandbox: write blocked outside project directory: {file_path}")
                return
        except (OSError, ValueError):
            _deny(f"Sandbox: invalid file path: {file_path}")
            return


def _is_env_file_access(tool_name: str, tool_input: dict[str, str]) -> bool:
    if tool_name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        name = Path(file_path).name
        if name.startswith(".env") and not any(name.endswith(s) for s in ENV_SAFE_SUFFIXES):
            return True

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if re.search(r"\.env\b(?!\.(?:sample|example|template|test|ci))", command):
            return True

    return False


def _sandbox_enabled(cwd: Path) -> bool:
    config_path = cwd / ".codemonkeys" / "config.json"
    if not config_path.exists():
        return False
    try:
        config: dict[str, object] = json.loads(config_path.read_text())
        return config.get("sandbox", False) is True
    except (json.JSONDecodeError, OSError):
        return False


def _deny(reason: str) -> None:
    output = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })
    print(output)


if __name__ == "__main__":
    main()
