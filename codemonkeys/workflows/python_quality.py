"""Python quality workflow — end-to-end code quality pipeline.

Runs deterministic CLI tools (ruff, mypy, pytest) and dispatches LLM
agents only when fixes or analysis are needed.

Usage:
    .venv/bin/python -m codemonkeys.workflows.python_quality
    .venv/bin/python -m codemonkeys.workflows.python_quality --skip-coverage
    .venv/bin/python -m codemonkeys.workflows.python_quality -o results.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.text import Text

from codemonkeys.agents import (
    DEPENDENCY_AUDITOR,
    FIXER,
    TEST_WRITER,
    make_code_reviewer,
    make_docs_reviewer,
    make_security_auditor,
)
from codemonkeys.runner import AgentRunner


_console = Console(stderr=True)


def _header(phase: int, title: str) -> None:
    _console.print(f"\n[bold cyan]Phase {phase}: {title}[/bold cyan]")
    _console.print("─" * 60)


def _run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, **kwargs,
    )


REQUIRED_TOOLS: dict[str, str] = {
    "ruff": "ruff",
    "mypy": "mypy",
    "pytest": "pytest",
    "pytest_cov": "pytest-cov",
    "pip_audit": "pip-audit",
}


def preflight_check() -> bool:
    """Check that all required tools are importable. Returns True if all present."""
    missing: list[str] = []
    for module, package in REQUIRED_TOOLS.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        _console.print(f"[red bold]Missing required tools: {', '.join(missing)}[/red bold]")
        _console.print(f"Install with: [bold]{sys.executable} -m pip install {' '.join(missing)}[/bold]")
        return False

    _console.print("[green]All required tools found.[/green]")
    return True


# ── Phase 1: Lint & Format ──────────────────────────────────────


def phase_lint_format() -> bool:
    """Run ruff fix + format. Returns True if any changes were made."""
    _header(1, "Lint & Format")

    fix = _run([sys.executable, "-m", "ruff", "check", "--fix", "."])
    fmt = _run([sys.executable, "-m", "ruff", "format", "."])

    changed = False
    if fix.stdout.strip():
        _console.print(f"  ruff fix: {fix.stdout.strip()}")
        changed = True
    else:
        _console.print("  ruff fix: no issues")

    if "file" in fmt.stdout.lower() or "reformatted" in fmt.stderr.lower():
        output = fmt.stderr.strip() or fmt.stdout.strip()
        _console.print(f"  ruff format: {output}")
        changed = True
    else:
        _console.print("  ruff format: no changes")

    return changed


# ── Phase 2: Test Coverage ──────────────────────────────────────


def _run_coverage() -> dict[str, Any] | None:
    """Run pytest with coverage and return the JSON report, or None."""
    with tempfile.TemporaryDirectory() as tmp:
        cov_json = Path(tmp) / "coverage.json"
        result = _run([
            sys.executable, "-m", "pytest",
            "--cov", "--cov-report", f"json:{cov_json}",
            "-q", "--no-header",
        ])
        _console.print(f"  pytest: {result.stdout.strip().splitlines()[-1] if result.stdout.strip() else 'no output'}")

        if cov_json.exists():
            return json.loads(cov_json.read_text(encoding="utf-8"))
    return None


def _extract_uncovered(cov_data: dict[str, Any], threshold: float = 90.0) -> str | None:
    """Extract uncovered lines from coverage JSON. Returns formatted string or None if above threshold."""
    totals = cov_data.get("totals", {})
    pct = totals.get("percent_covered", 100.0)
    _console.print(f"  coverage: {pct:.1f}%")

    if pct >= threshold:
        _console.print(f"  [green]Coverage is above {threshold}% — skipping test writer.[/green]")
        return None

    uncovered: list[str] = []
    for filepath, info in cov_data.get("files", {}).items():
        missing = info.get("missing_lines", [])
        if missing:
            uncovered.append(f"{filepath}: lines {missing}")

    if not uncovered:
        return None

    return "\n".join(uncovered)


async def phase_coverage(runner: AgentRunner) -> None:
    """Run coverage and dispatch test writer for uncovered code."""
    _header(2, "Test Coverage")

    cov_data = _run_coverage()
    if not cov_data:
        _console.print("  [yellow]Could not generate coverage report — skipping.[/yellow]")
        return

    uncovered = _extract_uncovered(cov_data)
    if not uncovered:
        return

    _console.print("  Dispatching test writer agent...")
    await runner.run_agent(
        TEST_WRITER,
        f"Write tests for the following uncovered code:\n\n{uncovered}",
    )
    _console.print("  [green]Test writer complete.[/green]")


# ── Phase 3: Type Check ────────────────────────────────────────


def _run_mypy() -> list[dict[str, Any]]:
    """Run mypy and return parsed JSON errors."""
    result = _run([sys.executable, "-m", "mypy", "--output", "json", "."])
    errors: list[dict[str, Any]] = []
    for line in (result.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            errors.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return errors


async def phase_type_check(runner: AgentRunner) -> list[dict[str, Any]]:
    """Run mypy, dispatch fixer if errors found. Returns error list."""
    _header(3, "Type Check")

    errors = _run_mypy()
    _console.print(f"  mypy: {len(errors)} error{'s' if len(errors) != 1 else ''}")

    if not errors:
        return []

    errors_json = json.dumps(errors, indent=2)
    _console.print("  Dispatching fixer agent...")
    await runner.run_agent(
        FIXER,
        f"Fix these mypy type errors:\n\n{errors_json}",
    )
    _console.print("  [green]Fixer complete.[/green]")
    return errors


# ── Phase 4: Test Regression ────────────────────────────────────


def _run_pytest() -> tuple[bool, str]:
    """Run pytest. Returns (passed, output)."""
    result = _run([
        sys.executable, "-m", "pytest",
        "-x", "-q", "--tb=short", "--no-header",
    ])
    passed = result.returncode == 0
    output = (result.stdout or "") + (result.stderr or "")
    return passed, output.strip()


async def phase_test_regression(runner: AgentRunner, max_iterations: int = 5) -> bool:
    """Run pytest in a loop, dispatching fixer on failures. Returns True if all tests pass."""
    _header(4, "Test Regression")

    prev_output: str | None = None
    for i in range(max_iterations):
        passed, output = _run_pytest()
        summary = output.splitlines()[-1] if output.strip() else "no output"
        _console.print(f"  iteration {i + 1}: {summary}")

        if passed:
            _console.print("  [green]All tests pass.[/green]")
            return True

        if prev_output is not None and output == prev_output:
            _console.print("  [yellow]No progress — same failures. Stopping.[/yellow]")
            return False

        prev_output = output
        _console.print("  Dispatching fixer agent...")
        await runner.run_agent(FIXER, f"Fix these test failures:\n\n{output}")
        _console.print("  [green]Fixer complete.[/green]")

    _console.print(f"  [yellow]Hit max iterations ({max_iterations}).[/yellow]")
    return False


# ── Phase 5: Code Review ───────────────────────────────────────


async def phase_code_review(runner: AgentRunner) -> str:
    """Run code reviewer + security auditor in sequence, then fix findings."""
    _header(5, "Code Review")

    _console.print("  Running code reviewer...")
    review_output = await runner.run_agent(
        make_code_reviewer(scope="repo"),
        "Review the code for logic errors, complexity, and design issues.",
    )

    _console.print("  Running security auditor...")
    security_output = await runner.run_agent(
        make_security_auditor(scope="repo"),
        "Audit the code for security vulnerabilities.",
    )

    combined = f"## Code Review Findings\n\n{review_output}\n\n## Security Audit Findings\n\n{security_output}"

    if not review_output.strip() and not security_output.strip():
        _console.print("  [green]No findings.[/green]")
        return combined

    _console.print("  Dispatching fixer agent...")
    await runner.run_agent(FIXER, f"Fix these findings:\n\n{combined}")
    _console.print("  [green]Fixer complete.[/green]")

    return combined


# ── Phase 6: Reports ────────────────────────────────────────────


async def phase_reports(runner: AgentRunner) -> dict[str, str]:
    """Run docs reviewer + dependency auditor. Read-only, no fixes."""
    _header(6, "Reports")

    _console.print("  Running docs reviewer...")
    docs_output = await runner.run_agent(
        make_docs_reviewer(scope="repo"),
        "Review documentation for drift against the code.",
    )

    _console.print("  Running dependency auditor...")
    dep_output = await runner.run_agent(
        DEPENDENCY_AUDITOR,
        "Audit dependencies for known vulnerabilities.",
    )

    return {"docs_review": docs_output, "dependency_audit": dep_output}


# ── Orchestrator ────────────────────────────────────────────────


async def run_quality_pipeline(
    *,
    skip_coverage: bool = False,
    max_fix_iterations: int = 5,
    output_file: str | None = None,
) -> dict[str, Any]:
    """Run the full quality pipeline and return a summary."""
    if not preflight_check():
        return {}

    runner = AgentRunner()
    results: dict[str, Any] = {}

    # Phase 1: Lint & Format (CLI only)
    results["lint_format"] = phase_lint_format()

    # Phase 2: Test Coverage (single pass)
    if not skip_coverage:
        await phase_coverage(runner)

    # Phase 3: Type Check (single pass)
    type_errors = await phase_type_check(runner)
    results["type_errors"] = len(type_errors)

    # Phase 4: Test Regression (iterate)
    tests_pass = await phase_test_regression(runner, max_iterations=max_fix_iterations)
    results["tests_pass"] = tests_pass

    # Phase 5: Code Review (single pass + fixer)
    review_output = await phase_code_review(runner)
    results["code_review"] = bool(review_output.strip())

    # Re-run phases 3-4 to catch regressions from code review fixes
    _console.print("\n[bold cyan]Re-checking after code review fixes...[/bold cyan]")
    _console.print("─" * 60)

    recheck_errors = _run_mypy()
    if recheck_errors:
        _console.print(f"  mypy: {len(recheck_errors)} new error{'s' if len(recheck_errors) != 1 else ''} — dispatching fixer...")
        await runner.run_agent(
            FIXER,
            f"Fix these mypy type errors:\n\n{json.dumps(recheck_errors, indent=2)}",
        )

    recheck_pass, _ = _run_pytest()
    if not recheck_pass:
        _console.print("  Tests failing after review fixes — running fix loop...")
        recheck_pass = await phase_test_regression(runner, max_iterations=3)
    results["final_tests_pass"] = recheck_pass

    # Phase 6: Reports (read-only)
    reports = await phase_reports(runner)
    results["reports"] = reports

    # Summary
    _console.print(f"\n{'═' * 60}")
    status = "[green]PASS[/green]" if recheck_pass else "[red]FAIL[/red]"
    _console.print(Text.from_markup(f"[bold]Quality pipeline complete — {status}[/bold]"))

    if output_file:
        Path(output_file).write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8",
        )
        _console.print(f"Results written to {output_file}")

    return results


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Python quality pipeline")
    parser.add_argument("--skip-coverage", action="store_true", help="Skip the coverage phase")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max fix iterations for test regression")
    parser.add_argument("-o", "--output", help="Write results to JSON file")
    args = parser.parse_args()

    asyncio.run(run_quality_pipeline(
        skip_coverage=args.skip_coverage,
        max_fix_iterations=args.max_iterations,
        output_file=args.output,
    ))
