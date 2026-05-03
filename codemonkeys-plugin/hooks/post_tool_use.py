"""PostToolUse hook — auto-format Python files with ruff after Edit/Write."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    data = json.loads(sys.stdin.read())
    tool_input = data.get("tool_input", {})
    cwd = Path(data.get("cwd", ".")).resolve()

    file_path = Path(tool_input.get("file_path", ""))
    if not file_path.suffix == ".py":
        sys.exit(0)

    resolved = file_path if file_path.is_absolute() else cwd / file_path
    if not resolved.exists():
        sys.exit(0)

    if not _ruff_available():
        warned_marker = cwd / ".codemonkeys" / ".ruff-warned"
        if not warned_marker.exists():
            warned_marker.parent.mkdir(parents=True, exist_ok=True)
            warned_marker.touch()
            print("⚠ ruff is not installed — auto-formatting disabled. Install with: pip install ruff")
        sys.exit(0)

    file_str = str(resolved)
    check_result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", file_str],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    format_result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", file_str],
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    changed = "1 file reformatted" in format_result.stderr or "Fixed" in check_result.stdout
    if changed:
        print(f"ruff: formatted `{file_path.name}`")


def _ruff_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


if __name__ == "__main__":
    main()
