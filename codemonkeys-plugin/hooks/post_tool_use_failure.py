"""PostToolUseFailure hook — log failed tool calls to JSONL."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    data = json.loads(sys.stdin.read())
    cwd = Path(data.get("cwd", ".")).resolve()

    log_dir = cwd / ".codemonkeys" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": data.get("tool_name", "unknown"),
        "input": data.get("tool_input", {}),
        "error": data.get("tool_response", data.get("error", "unknown")),
        "session_id": data.get("session_id", "unknown"),
    }

    with open(log_dir / "failures.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
