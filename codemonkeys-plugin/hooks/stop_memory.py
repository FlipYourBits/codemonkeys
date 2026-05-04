"""Stop hook — writes a lightweight project memory entry after sessions with significant changes."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SIGNIFICANT_THRESHOLD = 3
MEMORY_DIR = ".codemonkeys/memory"
MEMORY_INDEX = f"{MEMORY_DIR}/MEMORY.md"
MAX_INDEX_LINES = 50


def main() -> None:
    data = json.loads(sys.stdin.read())
    cwd = Path(data.get("cwd", ".")).resolve()

    diff_stat = _get_session_diff(cwd)
    if not diff_stat:
        sys.exit(0)

    files_changed = _parse_diff_stat(diff_stat)
    if len(files_changed) < SIGNIFICANT_THRESHOLD:
        sys.exit(0)

    summary = _build_summary(cwd, files_changed)
    _write_memory(cwd, summary)
    sys.exit(0)


def _get_session_diff(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.stdout.strip():
        return result.stdout.strip()

    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD~1", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def _parse_diff_stat(stat_output: str) -> list[str]:
    files: list[str] = []
    for line in stat_output.splitlines():
        if "|" in line:
            filename = line.split("|")[0].strip()
            if filename:
                files.append(filename)
    return files


def _build_summary(cwd: Path, files: list[str]) -> str:
    py_files = [f for f in files if f.endswith(".py")]
    test_files = [f for f in py_files if "test" in f]
    src_files = [f for f in py_files if "test" not in f]
    other_files = [f for f in files if not f.endswith(".py")]

    parts: list[str] = []
    if src_files:
        parts.append(f"src: {', '.join(src_files[:5])}")
        if len(src_files) > 5:
            parts.append(f"  (+{len(src_files) - 5} more)")
    if test_files:
        parts.append(f"tests: {', '.join(test_files[:3])}")
    if other_files:
        parts.append(f"other: {', '.join(other_files[:3])}")

    branch = _get_branch(cwd)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    header = f"## {date} — {branch}\n"
    return header + "\n".join(parts)


def _get_branch(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip() or "detached"


def _write_memory(cwd: Path, summary: str) -> None:
    memory_dir = cwd / MEMORY_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)

    index_path = cwd / MEMORY_INDEX
    existing = index_path.read_text() if index_path.exists() else ""
    lines = existing.strip().splitlines()

    lines.append(summary)

    if len(lines) > MAX_INDEX_LINES:
        lines = lines[-MAX_INDEX_LINES:]

    index_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
