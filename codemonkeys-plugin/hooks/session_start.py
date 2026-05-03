"""SessionStart hook — inject git state and clean up stale artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    data = json.loads(sys.stdin.read())
    cwd = Path(data.get("cwd", ".")).resolve()
    codemonkeys_dir = cwd / ".codemonkeys"

    _cleanup(codemonkeys_dir)

    if not _is_git_repo(cwd):
        sys.exit(0)

    branch = _run_git(["git", "branch", "--show-current"], cwd)
    status_lines = _run_git(["git", "status", "--porcelain"], cwd)
    change_count = len(status_lines.strip().splitlines()) if status_lines.strip() else 0
    log = _run_git(["git", "log", "--oneline", "-5"], cwd)

    output_parts = [f"[codemonkeys] branch: {branch.strip()} | {change_count} uncommitted changes"]
    if log.strip():
        lines = log.strip().splitlines()
        output_parts.append("Recent: " + lines[0])
        for line in lines[1:]:
            output_parts.append("        " + line)

    print("\n".join(output_parts))


def _is_git_repo(cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
    return result.stdout


def _cleanup(codemonkeys_dir: Path) -> None:
    for marker in [".ruff-warned", ".mypy-warned", ".pytest-warned", ".active-skill"]:
        (codemonkeys_dir / marker).unlink(missing_ok=True)

    attempt_file = codemonkeys_dir / "stop-gate" / "attempt-count"
    attempt_file.unlink(missing_ok=True)

    failures_file = codemonkeys_dir / "logs" / "failures.jsonl"
    if failures_file.exists():
        lines = failures_file.read_text().splitlines()
        if len(lines) > 500:
            failures_file.write_text("\n".join(lines[-500:]) + "\n")


if __name__ == "__main__":
    main()
