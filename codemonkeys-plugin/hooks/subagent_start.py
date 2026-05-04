"""SubagentStart hook — log sub-agent spawn events."""
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
        "event": "start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id", "unknown"),
        "agent_name": data.get("agent_name", "unknown"),
    }

    with open(log_dir / "subagents.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"[codemonkeys] subagent started: {record['agent_name']}")


if __name__ == "__main__":
    main()
