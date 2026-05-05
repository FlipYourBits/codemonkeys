"""Action phases — triage, fix, verify, report (shared tail for all workflows)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


async def triage(ctx: WorkflowContext) -> dict[str, list[FixRequest]]:
    """Collect all findings, deduplicate, and create fix requests.

    In auto_fix mode (AUTOMATED): selects all high + medium severity findings.
    In interactive mode (GATE): uses ctx.user_input if provided, else selects all.
    """
    config = ctx.config
    all_findings: dict[str, list[Finding]] = {}

    # Collect from file_review
    file_findings: list[FileFindings] = ctx.phase_results.get("file_review", {}).get(
        "file_findings", []
    )
    for ff in file_findings:
        for f in ff.findings:
            all_findings.setdefault(f.file, []).append(f)

    # Collect from doc_review
    doc_findings: list[FileFindings] = ctx.phase_results.get("doc_review", {}).get(
        "doc_findings", []
    )
    for ff in doc_findings:
        for f in ff.findings:
            all_findings.setdefault(f.file, []).append(f)

    # Collect from architecture_review (convert ArchitectureFinding -> Finding)
    arch_findings = ctx.phase_results.get("architecture_review", {}).get(
        "architecture_findings"
    )
    if arch_findings:
        for af in arch_findings.findings:
            finding = Finding(
                file=af.files[0] if af.files else "",
                line=None,
                severity=af.severity,
                category="quality",
                subcategory=af.subcategory,
                title=af.title,
                description=af.description,
                suggestion=af.suggestion,
                source="architecture-reviewer",
            )
            all_findings.setdefault(finding.file, []).append(finding)

    if config.auto_fix:
        fix_requests = []
        for file, findings in all_findings.items():
            fixable = [f for f in findings if f.severity in ("high", "medium")]
            if fixable:
                fix_requests.append(FixRequest(file=file, findings=fixable))
        return {"fix_requests": fix_requests}

    if ctx.user_input is not None:
        return {"fix_requests": ctx.user_input}

    # Default: all findings
    fix_requests = []
    for file, findings in all_findings.items():
        if findings:
            fix_requests.append(FixRequest(file=file, findings=findings))
    return {"fix_requests": fix_requests}


async def fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
    """Dispatch code fixer per file."""
    fix_requests: list[FixRequest] = ctx.phase_results["triage"]["fix_requests"]
    runner = AgentRunner(cwd=ctx.cwd)
    results: list[FixResult] = []

    for request in fix_requests:
        findings_json = request.model_dump_json(indent=2)
        agent = make_python_code_fixer(request.file, findings_json)
        output_format = {
            "type": "json_schema",
            "schema": FixResult.model_json_schema(),
        }
        await runner.run_agent(
            agent, f"Fix findings in {request.file}", output_format=output_format
        )
        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            result = FixResult.model_validate(structured)
        else:
            result = FixResult(
                file=request.file, fixed=[], skipped=["Could not parse agent output"]
            )
        results.append(result)

    return {"fix_results": results}


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
