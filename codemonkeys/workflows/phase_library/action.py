"""Action phases — triage, fix, verify, report (shared tail for all workflows)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.mechanical import MechanicalAuditResult
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from claude_agent_sdk import AgentDefinition
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.events import (
    EventType,
    FindingsSummaryPayload,
    FixProgressPayload,
    TriageReadyPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


def _collect_mechanical_findings(
    mechanical: MechanicalAuditResult,
) -> list[Finding]:
    """Convert mechanical audit results into common Finding format."""
    findings: list[Finding] = []

    for rf in mechanical.ruff:
        findings.append(
            Finding(
                file=rf.file,
                line=rf.line,
                severity="low",
                category="style",
                subcategory=rf.code,
                title=f"Ruff {rf.code}: {rf.message}",
                description=rf.message,
                suggestion=None,
                source="ruff",
            )
        )

    for pf in mechanical.pyright:
        severity = "medium" if pf.severity == "error" else "low"
        findings.append(
            Finding(
                file=pf.file,
                line=pf.line,
                severity=severity,
                category="quality",
                subcategory="type_error",
                title=f"Pyright: {pf.message[:80]}",
                description=pf.message,
                suggestion=None,
                source="pyright",
            )
        )

    for sf in mechanical.secrets:
        findings.append(
            Finding(
                file=sf.file,
                line=sf.line,
                severity="high",
                category="security",
                subcategory="secret_detected",
                title=f"Potential secret: {sf.pattern}",
                description=f"Pattern '{sf.pattern}' matched in {sf.file}:{sf.line}",
                suggestion="Remove the secret and use environment variables or a secrets manager.",
                source="secrets-scanner",
            )
        )

    if mechanical.pip_audit:
        for cve in mechanical.pip_audit:
            findings.append(
                Finding(
                    file="pyproject.toml",
                    line=None,
                    severity=cve.severity
                    if cve.severity in ("high", "medium", "low")
                    else "medium",
                    category="security",
                    subcategory="cve",
                    title=f"{cve.cve_id}: {cve.package} {cve.installed_version}",
                    description=cve.description,
                    suggestion=f"Upgrade to {cve.fixed_version}"
                    if cve.fixed_version
                    else None,
                    source="pip-audit",
                )
            )

    return findings


def _collect_spec_compliance_findings(
    spec_findings: SpecComplianceFindings,
) -> list[Finding]:
    """Convert spec compliance findings into common Finding format."""
    findings: list[Finding] = []

    for sf in spec_findings.findings:
        findings.append(
            Finding(
                file=sf.files[0] if sf.files else "",
                line=None,
                severity=sf.severity,
                category="quality",
                subcategory=sf.category,
                title=sf.title,
                description=sf.description,
                suggestion=sf.suggestion,
                source="spec-compliance-reviewer",
            )
        )

    return findings


async def _nlp_triage(
    user_text: str,
    all_findings: dict[str, list[Finding]],
    ctx: WorkflowContext,
) -> list[FixRequest]:
    """Use a haiku agent to translate natural language into fix selections."""
    flat_findings = []
    for file, findings in all_findings.items():
        for f in findings:
            flat_findings.append(f)

    findings_summary = json.dumps(
        [{"idx": i + 1, **f.model_dump()} for i, f in enumerate(flat_findings)],
        indent=2,
    )

    triage_prompt = f"""\
Here are the code review findings:

{findings_summary}

The user said: "{user_text}"

Based on the user's instruction, return a JSON array of objects, each with:
- "file": the file path
- "finding_indices": array of 1-based finding indices to fix in that file

Group findings by file. Only include findings the user wants to fix.
Return ONLY the JSON array, no explanation."""

    agent = AgentDefinition(
        description="Triage filter",
        prompt="You translate natural language triage instructions into structured selections. Return only valid JSON.",
        model="haiku",
        tools=[],
        permissionMode="dontAsk",
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    result = await runner.run_agent(agent, triage_prompt, log_name="nlp_triage")

    raw = result.text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        selections = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        selections = None

    if selections is None:
        fix_requests = []
        for file, findings in all_findings.items():
            if findings:
                fix_requests.append(FixRequest(file=file, findings=findings))
        return fix_requests

    fix_requests = []
    for sel in selections:
        file_path = sel["file"]
        indices = sel.get("finding_indices", [])
        matched = [
            flat_findings[i - 1] for i in indices if 1 <= i <= len(flat_findings)
        ]
        if matched:
            fix_requests.append(FixRequest(file=file_path, findings=matched))

    return fix_requests


async def triage(ctx: WorkflowContext) -> dict[str, list[FixRequest]]:
    """Collect all findings, deduplicate, and create fix requests.

    In auto_fix mode (AUTOMATED): selects all high + medium severity findings.
    In interactive mode (GATE): uses ctx.user_input if provided, else selects all.
    """
    config = ctx.config
    all_findings: dict[str, list[Finding]] = {}

    # Collect from mechanical_audit
    mechanical: MechanicalAuditResult | None = ctx.phase_results.get(
        "mechanical_audit", {}
    ).get("mechanical")
    if mechanical:
        for f in _collect_mechanical_findings(mechanical):
            all_findings.setdefault(f.file, []).append(f)

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

    # Collect from spec_compliance_review
    spec_compliance: SpecComplianceFindings | None = ctx.phase_results.get(
        "spec_compliance_review", {}
    ).get("spec_findings")
    if spec_compliance:
        for f in _collect_spec_compliance_findings(spec_compliance):
            all_findings.setdefault(f.file, []).append(f)

    # Deduplicate: if a mechanical tool (ruff/pyright) and an agent reviewer both
    # reported the same file+line issue, keep the richer agent finding.
    mechanical_sources = {"ruff", "pyright", "secrets-scanner", "pip-audit"}
    for file, findings in all_findings.items():
        agent_keys: set[tuple[int | None, str]] = set()
        for f in findings:
            if f.source not in mechanical_sources:
                agent_keys.add((f.line, f.subcategory))
        deduped = [
            f
            for f in findings
            if f.source not in mechanical_sources
            or (f.line, f.subcategory) not in agent_keys
        ]
        all_findings[file] = deduped

    # Emit triage events
    total = sum(len(fs) for fs in all_findings.values())
    fixable = sum(
        1
        for fs in all_findings.values()
        for f in fs
        if f.severity in ("high", "medium")
    )

    if ctx.emitter:
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for fs in all_findings.values():
            for f in fs:
                by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
                by_category[f.category] = by_category.get(f.category, 0) + 1
        ctx.emitter.emit(
            EventType.FINDINGS_SUMMARY,
            FindingsSummaryPayload(
                total=total, by_severity=by_severity, by_category=by_category
            ),
        )
        ctx.emitter.emit(
            EventType.TRIAGE_READY,
            TriageReadyPayload(findings_count=total, fixable_count=fixable),
        )

    if config.auto_fix:
        fix_requests = []
        for file, findings in all_findings.items():
            fixable_findings = [f for f in findings if f.severity in ("high", "medium")]
            if fixable_findings:
                fix_requests.append(FixRequest(file=file, findings=fixable_findings))
        return {"fix_requests": fix_requests}

    if ctx.user_input is not None:
        if isinstance(ctx.user_input, str):
            fix_requests = await _nlp_triage(ctx.user_input, all_findings, ctx)
            return {"fix_requests": fix_requests}
        return {"fix_requests": ctx.user_input}

    # Default: all findings
    fix_requests = []
    for file, findings in all_findings.items():
        if findings:
            fix_requests.append(FixRequest(file=file, findings=findings))
    return {"fix_requests": fix_requests}


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
            log_name=f"fix__{request.file}",
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
