"""Test-coverage node: runs a coverage tool and emits per-file uncovered
ranges as `missing_coverage` findings. Deterministic — no LLM call.

v1 supports Python (`pytest --cov` producing coverage.json). Extending to
other runners means adding a parser branch in `_collect_uncovered`.

In diff mode, only lines belonging to files changed since `base_ref` are
flagged. In full mode, every uncovered line in the project is flagged.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

Mode = Literal["diff", "full"]


def _run(argv: list[str], cwd: str, timeout: int = 600) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _changed_files(cwd: str, base_ref: str) -> set[str]:
    if not shutil.which("git"):
        return set()
    _, stdout, _ = _run(["git", "diff", "--name-only", f"{base_ref}...HEAD"], cwd, 30)
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def _condense_ranges(lines: list[int]) -> list[tuple[int, int]]:
    """[1,2,3,7,8] -> [(1,3),(7,8)]."""
    if not lines:
        return []
    lines = sorted(set(lines))
    ranges: list[tuple[int, int]] = []
    start = end = lines[0]
    for n in lines[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append((start, end))
            start = end = n
    ranges.append((start, end))
    return ranges


def _pytest_cov(cwd: str, report_path: Path) -> dict[str, Any] | None:
    """Run pytest with coverage and load the JSON report."""
    if not shutil.which("pytest") and not shutil.which("py.test"):
        return None
    code, _, _ = _run(
        [
            "pytest",
            "--cov",
            f"--cov-report=json:{report_path}",
            "--cov-report=",
            "-q",
            "--no-header",
        ],
        cwd,
    )
    # Non-zero is fine — we want the coverage file even if some tests failed.
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text())
    except json.JSONDecodeError:
        return None


def _findings_from_coverage_json(
    data: dict[str, Any], scope_files: set[str] | None
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for file_path, file_data in (data.get("files") or {}).items():
        if scope_files is not None and file_path not in scope_files:
            continue
        missing = file_data.get("missing_lines") or []
        if not missing:
            continue
        for start, end in _condense_ranges(missing):
            count = end - start + 1
            findings.append(
                {
                    "file": file_path,
                    "line": start,
                    "severity": "LOW",
                    "category": "missing_coverage",
                    "source": "pytest-cov",
                    "description": (
                        f"{count} uncovered line(s) at {file_path}:{start}"
                        + (f"-{end}" if end != start else "")
                    ),
                    "recommendation": "Add a test exercising this branch.",
                    "confidence": 1.0,
                    "line_end": end,
                }
            )
    return findings


def py_test_coverage_node(
    *,
    name: str = "test_coverage",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    output_key: str = "coverage_findings",
    cwd_key: str = "working_dir",
    report_filename: str = ".langclaude-coverage.json",
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a deterministic test-coverage node (Python / pytest-cov).

    State input:
        `cwd_key`: repo root.
        `base_ref_key`: required in diff mode; ignored in full mode.

    State output:
        `output_key`: list of finding dicts. Empty if pytest/coverage
            aren't installed or no source files are changed.
        "coverage_summary": {"files_reviewed", "uncovered_findings"}.

    Notes:
        - Runs `pytest --cov --cov-report=json:<file>` in the repo. Tests
          have side effects — only use this on a clean tree or in a
          dedicated CI step.
        - The JSON report is written to `<cwd>/<report_filename>`. Add
          that filename to your `.gitignore`.
    """

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get(cwd_key) or "."
        report_path = Path(cwd) / report_filename
        data = await asyncio.to_thread(_pytest_cov, cwd, report_path)
        if data is None:
            return {
                output_key: [],
                "coverage_summary": {"files_reviewed": 0, "uncovered_findings": 0},
            }

        scope_files: set[str] | None = None
        if mode == "diff":
            base_ref = state.get(base_ref_key) or "main"
            scope_files = await asyncio.to_thread(_changed_files, cwd, base_ref)

        findings = _findings_from_coverage_json(data, scope_files)
        files_reviewed = len(
            {f for f in (data.get("files") or {}) if scope_files is None or f in scope_files}
        )
        return {
            output_key: findings,
            "coverage_summary": {
                "files_reviewed": files_reviewed,
                "uncovered_findings": len(findings),
            },
        }

    run.__name__ = name
    run.declared_outputs = (output_key, "coverage_summary")  # type: ignore[attr-defined]
    return run
