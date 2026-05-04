"""Notification hook — desktop alert when Claude needs attention."""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    data = json.loads(sys.stdin.read())
    message = data.get("message", "Claude needs your attention")

    try:
        subprocess.run(
            [
                "notify-send",
                "--urgency=normal",
                "--app-name=Claude Code",
                "Claude Code",
                message,
            ],
            timeout=5,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    main()
