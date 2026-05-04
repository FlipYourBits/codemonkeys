"""SubagentStop hook — log completion and verify tests for python-implementer."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERIFIED_AGENTS = {"python-implementer"}


def main() -> None:
    data = json.loads(sys.stdin.read())
    cwd = Path(data.get("cwd", ".")).resolve()
    codemonkeys_dir = cwd / ".codemonkeys"
    agent_name = data.get("agent_name", "unknown")

    _log_event(codemonkeys_dir, data, agent_name)

    if agent_name not in VERIFIED_AGENTS:
        print(f"[codemonkeys] subagent completed: {agent_name}")
        sys.exit(0)

    if not _pytest_available():
        print(f"[codemonkeys] subagent completed: {agent_name} (pytest not installed, skipping verification)")
        sys.exit(0)

    NO_TESTS_COLLECTED = 5

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short", "--no-header"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode in (0, NO_TESTS_COLLECTED):
        print(f"[codemonkeys] subagent completed: {agent_name} — tests passed")
        sys.exit(0)

    failure_output = (result.stdout + result.stderr).strip()
    print(
        f"[codemonkeys] {agent_name} finished but tests are failing. "
        f"Fix before continuing:\n{failure_output}",
        file=sys.stderr,
    )
    sys.exit(2)


def _log_event(codemonkeys_dir: Path, data: dict, agent_name: str) -> None:
    log_dir = codemonkeys_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "event": "stop",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id", "unknown"),
        "agent_name": agent_name,
    }

    with open(log_dir / "subagents.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def _pytest_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


if __name__ == "__main__":
    main()
