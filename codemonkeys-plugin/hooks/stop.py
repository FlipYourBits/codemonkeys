"""Stop hook — quality gate that blocks completion if tests fail (max 2 attempts)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    data = json.loads(sys.stdin.read())
    cwd = Path(data.get("cwd", ".")).resolve()
    codemonkeys_dir = cwd / ".codemonkeys"

    active_skill = codemonkeys_dir / ".active-skill"
    if not active_skill.exists():
        sys.exit(0)

    if not _pytest_available():
        warned_marker = codemonkeys_dir / ".pytest-warned"
        if not warned_marker.exists():
            warned_marker.parent.mkdir(parents=True, exist_ok=True)
            warned_marker.touch()
            print("⚠ pytest is not installed — quality gate disabled. Install with: pip install pytest")
        sys.exit(0)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short", "--no-header"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        _reset_attempts(codemonkeys_dir)
        sys.exit(0)

    failure_output = result.stdout + result.stderr
    attempts = _read_attempts(codemonkeys_dir)
    attempts += 1
    _write_attempts(codemonkeys_dir, attempts)

    if attempts < 2:
        print(
            f"Tests failing — fix before completing. Attempt {attempts}/2:\n{failure_output}",
            file=sys.stderr,
        )
        sys.exit(2)
    else:
        _reset_attempts(codemonkeys_dir)
        active_skill.unlink(missing_ok=True)
        print(f"Tests still failing after 2 attempts. Remaining failures:\n{failure_output}")
        sys.exit(0)


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


def _read_attempts(codemonkeys_dir: Path) -> int:
    attempt_file = codemonkeys_dir / "stop-gate" / "attempt-count"
    if attempt_file.exists():
        try:
            return int(attempt_file.read_text().strip())
        except (ValueError, OSError):
            return 0
    return 0


def _write_attempts(codemonkeys_dir: Path, count: int) -> None:
    gate_dir = codemonkeys_dir / "stop-gate"
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / "attempt-count").write_text(str(count))


def _reset_attempts(codemonkeys_dir: Path) -> None:
    attempt_file = codemonkeys_dir / "stop-gate" / "attempt-count"
    attempt_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
