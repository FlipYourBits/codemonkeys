"""Action phases — fix, verify, report (shared tail for all workflows).

Triage logic lives in _action_triage.py; re-exported here for backwards compat.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.findings import FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.events import EventType, FixProgressPayload
from codemonkeys.workflows.phases import WorkflowContext
from codemonkeys.workflows.phase_library._action_triage import triage  # re-export

__all__ = ["triage", "fix", "verify", "report"]

PYTHON = sys.executable


async def _fix_one_file(
    request: FixRequest,
    cwd: str,
    emitter: Any,
    semaphore: asyncio.Semaphore,
    log_dir: Any = None,
) -> FixResult:
    """Fix a single file under the concurrency semaphore."""
    async with semaphore:
        if emitter:
            emitter.emit(
                EventType.FIX_PROGRESS,
                FixProgressPayload(file=request.file, status="started"),
            )

        runner = AgentRunner(cwd=cwd, emitter=emitter, log_dir=log_dir)
        findings_json = request.model_dump_json(indent=2)
        agent = make_python_code_fixer(request.file, findings_json)
        output_format = {
            "type": "json_schema",
            "schema": FixResult.model_json_schema(),
        }
        result = await runner.run_agent(
            agent,
            f"Fix findings in {request.file}",
            output_format=output_format,
            agent_name="python_code_fixer",
            files=request.file,
        )
        if result.structured:
            fix_result = FixResult.model_validate(result.structured)
        else:
            fix_result = FixResult(
                file=request.file, fixed=[], skipped=["Could not parse agent output"]
            )

        if emitter:
            status = "completed" if fix_result.fixed else "failed"
            emitter.emit(
                EventType.FIX_PROGRESS,
                FixProgressPayload(file=request.file, status=status),
            )

        return fix_result


async def fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
    """Dispatch code fixers in parallel (one per file)."""
    fix_requests: list[FixRequest] = ctx.phase_results["triage"]["fix_requests"]
    config = ctx.config
    semaphore = asyncio.Semaphore(config.max_concurrent)

    tasks = [
        _fix_one_file(request, ctx.cwd, ctx.emitter, semaphore, ctx.log_dir)
        for request in fix_requests
    ]
    results = await asyncio.gather(*tasks)

    return {"fix_results": list(results)}


async def verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    """Run pytest, ruff, pyright to verify fixes didn't break anything."""
    cwd = Path(ctx.cwd)

    tests = subprocess.run(
        [PYTHON, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    lint = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    typecheck = subprocess.run(
        [PYTHON, "-m", "pyright", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    errors = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")
    if typecheck.returncode != 0:
        errors.append(f"pyright: {typecheck.stdout[:500]}")

    result = VerificationResult(
        tests_passed=tests.returncode == 0,
        lint_passed=lint.returncode == 0,
        typecheck_passed=typecheck.returncode == 0,
        errors=errors,
    )
    return {"verification": result}


async def report(ctx: WorkflowContext) -> dict[str, Any]:
    """Summarize the review run."""
    fix_results: list[FixResult] = ctx.phase_results.get("fix", {}).get(
        "fix_results", []
    )
    verification: VerificationResult | None = ctx.phase_results.get("verify", {}).get(
        "verification"
    )

    fixed_count = sum(len(r.fixed) for r in fix_results)
    skipped_count = sum(len(r.skipped) for r in fix_results)

    return {
        "summary": {
            "fixed": fixed_count,
            "skipped": skipped_count,
            "tests_passed": verification.tests_passed if verification else None,
            "lint_passed": verification.lint_passed if verification else None,
            "typecheck_passed": verification.typecheck_passed if verification else None,
        }
    }
