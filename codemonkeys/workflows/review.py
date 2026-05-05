"""Review workflow — discover, review, architecture, triage, fix, verify."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings
from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.core.analysis import analyze_files, format_analysis
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def make_review_workflow(*, auto_fix: bool = False) -> Workflow:
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=_discover),
            Phase(name="review", phase_type=PhaseType.AUTOMATED, execute=_review),
            Phase(
                name="architecture",
                phase_type=PhaseType.AUTOMATED,
                execute=_architecture,
            ),
            Phase(name="triage", phase_type=triage_type, execute=_triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=_fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=_verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=_report),
        ],
    )


async def _discover(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)

    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
    else:
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(
                part in p.parts
                for part in ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
            )
        ]

    mechanical: dict[str, Any] = {}
    python = sys.executable

    for tool, cmd in [
        ("ruff", [python, "-m", "ruff", "check", "--output-format=json", "."]),
        ("pytest", [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"]),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        mechanical[tool] = {
            "returncode": r.returncode,
            "stdout": r.stdout[:2000],
            "stderr": r.stderr[:500],
        }

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)

    return {"files": files, "mechanical": mechanical, "structural_metadata": structural_metadata}


async def _review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    from codemonkeys.core.runner import AgentRunner

    files = ctx.phase_results["discover"]["files"]
    runner = AgentRunner(cwd=ctx.cwd)
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")
    all_findings: list[FileFindings] = []

    for file_path in files:
        agent = make_python_file_reviewer([file_path])
        output_format = {
            "type": "json_schema",
            "schema": FileFindings.model_json_schema(),
        }
        raw = await runner.run_agent(
            agent, f"Review: {file_path}", output_format=output_format
        )

        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            findings = FileFindings.model_validate(structured)
        else:
            try:
                findings = FileFindings.model_validate_json(raw)
            except Exception:
                findings = FileFindings(
                    file=file_path, summary="Could not parse output", findings=[]
                )

        all_findings.append(findings)
        safe_name = file_path.replace("/", "__").replace("\\", "__")
        store.save(ctx.run_id, f"findings/{safe_name}", findings)

    return {"findings": all_findings}


async def _architecture(ctx: WorkflowContext) -> dict[str, ArchitectureFindings]:
    from codemonkeys.core.runner import AgentRunner

    files: list[str] = ctx.phase_results["discover"]["files"]
    structural_metadata: str = ctx.phase_results["discover"]["structural_metadata"]
    per_file_findings: list[FileFindings] = ctx.phase_results["review"]["findings"]

    file_summaries = [{"file": f.file, "summary": f.summary} for f in per_file_findings]

    agent = make_architecture_reviewer(
        files=files,
        file_summaries=file_summaries,
        structural_metadata=structural_metadata,
    )
    runner = AgentRunner(cwd=ctx.cwd)
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")

    output_format = {
        "type": "json_schema",
        "schema": ArchitectureFindings.model_json_schema(),
    }
    raw = await runner.run_agent(
        agent,
        "Review the codebase for cross-file design issues.",
        output_format=output_format,
    )

    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        findings = ArchitectureFindings.model_validate(structured)
    else:
        try:
            findings = ArchitectureFindings.model_validate_json(raw)
        except Exception:
            findings = ArchitectureFindings(files_reviewed=files, findings=[])

    store.save(ctx.run_id, "architecture-findings", findings)
    return {"architecture_findings": findings}


async def _triage(ctx: WorkflowContext) -> dict[str, list[FixRequest]]:
    if ctx.user_input is not None:
        return {"fix_requests": ctx.user_input}

    per_file_findings: list[FileFindings] = ctx.phase_results["review"]["findings"]
    fix_requests = []
    for ff in per_file_findings:
        if ff.findings:
            fix_requests.append(FixRequest(file=ff.file, findings=ff.findings))
    return {"fix_requests": fix_requests}


async def _fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
    from codemonkeys.core.runner import AgentRunner

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
            agent,
            f"Fix findings in {request.file}",
            output_format=output_format,
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


async def _verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    cwd = Path(ctx.cwd)
    python = sys.executable

    tests = subprocess.run(
        [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    lint = subprocess.run(
        [python, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    typecheck = subprocess.run(
        [python, "-m", "pyright", "."],
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


async def _report(ctx: WorkflowContext) -> dict[str, Any]:
    fix_results = ctx.phase_results.get("fix", {}).get("fix_results", [])
    verification = ctx.phase_results.get("verify", {}).get("verification")

    fixed_count = sum(len(r.fixed) for r in fix_results)
    skipped_count = sum(len(r.skipped) for r in fix_results)

    return {
        "summary": {
            "fixed": fixed_count,
            "skipped": skipped_count,
            "tests_passed": verification.tests_passed if verification else None,
            "lint_passed": verification.lint_passed if verification else None,
        }
    }
