"""Mechanical audit phase — runs subprocess tools and returns structured results."""

from __future__ import annotations

import time
from pathlib import Path

from codemonkeys.artifacts.schemas.mechanical import MechanicalAuditResult
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext
from codemonkeys.workflows.phase_library._mechanical_hygiene import _run_release_hygiene
from codemonkeys.workflows.phase_library._mechanical_license import (
    _run_license_compliance,
)
from codemonkeys.workflows.phase_library._mechanical_tools import (
    _compute_coverage,
    _find_dead_code,
    _run_pip_audit,
    _run_pyright,
    _run_pytest,
    _run_ruff,
    _scan_secrets,
)


async def mechanical_audit(ctx: WorkflowContext) -> dict[str, MechanicalAuditResult]:
    """Run enabled mechanical audit tools and return structured results."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]
    enabled: set[str] = ctx.config.audit_tools
    emitter = ctx.emitter

    ruff_findings = []
    pyright_findings = []
    pytest_result = None
    pip_audit_findings = None
    secrets_findings = []
    coverage_map = None
    dead_code_findings = None
    license_compliance_findings = None
    release_hygiene_findings = None

    def _emit_start(tool: str) -> float:
        if emitter:
            emitter.emit(
                EventType.MECHANICAL_TOOL_STARTED,
                MechanicalToolStartedPayload(tool=tool, files_count=len(files)),
            )
        return time.time()

    def _emit_done(tool: str, start: float, count: int) -> None:
        if emitter:
            emitter.emit(
                EventType.MECHANICAL_TOOL_COMPLETED,
                MechanicalToolCompletedPayload(
                    tool=tool,
                    findings_count=count,
                    duration_ms=int((time.time() - start) * 1000),
                ),
            )

    if "ruff" in enabled:
        t = _emit_start("ruff")
        ruff_findings = _run_ruff(files, cwd)
        _emit_done("ruff", t, len(ruff_findings))

    if "pyright" in enabled:
        t = _emit_start("pyright")
        pyright_findings = _run_pyright(files, cwd)
        _emit_done("pyright", t, len(pyright_findings))

    if "pytest" in enabled:
        t = _emit_start("pytest")
        pytest_result = _run_pytest(cwd)
        _emit_done("pytest", t, pytest_result.failed + pytest_result.errors)

    if "pip_audit" in enabled:
        t = _emit_start("pip_audit")
        pip_audit_findings = _run_pip_audit(cwd)
        _emit_done("pip_audit", t, len(pip_audit_findings))

    if "secrets" in enabled:
        t = _emit_start("secrets")
        secrets_findings = _scan_secrets(files, cwd)
        _emit_done("secrets", t, len(secrets_findings))

    if "coverage" in enabled:
        t = _emit_start("coverage")
        coverage_map = _compute_coverage(files, cwd)
        _emit_done("coverage", t, len(coverage_map.uncovered))

    if "dead_code" in enabled:
        t = _emit_start("dead_code")
        dead_code_findings = _find_dead_code(files, cwd)
        _emit_done("dead_code", t, len(dead_code_findings))

    if "license_compliance" in enabled:
        t = _emit_start("license_compliance")
        license_compliance_findings = _run_license_compliance(cwd)
        _emit_done("license_compliance", t, len(license_compliance_findings))

    if "release_hygiene" in enabled:
        t = _emit_start("release_hygiene")
        release_hygiene_findings = _run_release_hygiene(files, cwd)
        _emit_done("release_hygiene", t, len(release_hygiene_findings))

    return {
        "mechanical": MechanicalAuditResult(
            ruff=ruff_findings,
            pyright=pyright_findings,
            pytest=pytest_result,
            pip_audit=pip_audit_findings,
            secrets=secrets_findings,
            coverage=coverage_map,
            dead_code=dead_code_findings,
            license_compliance=license_compliance_findings,
            release_hygiene=release_hygiene_findings,
        )
    }
