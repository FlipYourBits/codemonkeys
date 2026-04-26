"""Test-runner node: runs the project's test suite and reports failures
as findings. Deterministic — no LLM call.

Failing tests come back as `category: "failing_test"` findings. The
intent is *report only* — feed these into `claude_bug_fixer_node` for root-cause
analysis rather than into `claude_issue_fixer_node` (auto-fixing failing tests
is a known footgun: the agent may weaken assertions instead of fixing
the bug).

v1 supports pytest. Extending to other runners means adding a parser
branch in `_parse_pytest_json`-style helpers.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


def _run(argv: list[str], cwd: str, timeout: int = 600) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _pytest_json(cwd: str, report_path: Path) -> dict[str, Any] | None:
    """Run pytest with the json-report plugin if available."""
    if not (shutil.which("pytest") or shutil.which("py.test")):
        return None
    code, _, _ = _run(
        [
            "pytest",
            f"--json-report",
            f"--json-report-file={report_path}",
            "-q",
            "--no-header",
        ],
        cwd,
    )
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text())
    except json.JSONDecodeError:
        return None


def _findings_from_pytest_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for test in data.get("tests") or []:
        outcome = test.get("outcome")
        if outcome not in ("failed", "error"):
            continue
        nodeid = test.get("nodeid", "")
        location = test.get("location") or [None, None, None]
        file_path = location[0] or nodeid.split("::", 1)[0]
        line = location[1] or 0
        call = test.get("call") or {}
        longrepr = (call.get("longrepr") or "").strip()
        first_line = longrepr.splitlines()[0] if longrepr else "test failed"
        findings.append(
            {
                "file": file_path,
                "line": int(line) + 1 if isinstance(line, int) else 0,
                "severity": "HIGH" if outcome == "failed" else "MEDIUM",
                "category": "failing_test",
                "source": "pytest",
                "description": f"{nodeid} {outcome}: {first_line}",
                "recommendation": (
                    "Investigate the failure with claude_bug_fixer_node — root-cause "
                    "the bug, do not weaken the assertion."
                ),
                "confidence": 1.0,
                "nodeid": nodeid,
                "traceback": longrepr,
            }
        )
    return findings


def py_test_runner_node(
    *,
    name: str = "test_runner",
    output_key: str = "test_findings",
    cwd_key: str = "working_dir",
    report_filename: str = ".langclaude-pytest.json",
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a deterministic test-runner node (Python / pytest).

    State input:
        `cwd_key`: repo root.

    State output:
        `output_key`: list of finding dicts (one per failing test).
            Empty when all tests pass or pytest isn't installed.
        "test_summary": {"passed", "failed", "errors", "skipped"}.

    Notes:
        - Requires `pytest-json-report`. Install with `pip install
          pytest-json-report`. If missing, the node returns an empty
          result with a hint in `test_summary["error"]`.
        - Tests have side effects — only use on a clean tree or in CI.
        - Failing-test findings are intended for `claude_bug_fixer_node`, not
          `claude_issue_fixer_node`. Auto-applying fixes for failing tests is
          dangerous (the agent may weaken assertions instead of fixing
          the underlying bug).
    """

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get(cwd_key) or "."
        report_path = Path(cwd) / report_filename
        data = await asyncio.to_thread(_pytest_json, cwd, report_path)
        if data is None:
            return {
                output_key: [],
                "test_summary": {
                    "error": "pytest or pytest-json-report not available",
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                },
            }

        findings = _findings_from_pytest_json(data)
        summary = data.get("summary") or {}
        return {
            output_key: findings,
            "test_summary": {
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "errors": summary.get("error", 0),
                "skipped": summary.get("skipped", 0),
            },
        }

    run.__name__ = name
    run.declared_outputs = (output_key, "test_summary")  # type: ignore[attr-defined]
    return run
