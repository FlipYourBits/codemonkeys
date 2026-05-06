"""Stabilize phases — build check, dependency health, and coverage measurement."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage
from codemonkeys.artifacts.schemas.health import (
    BuildCheckResult,
    DependencyHealthResult,
    OutdatedPackage,
)
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


def _emit_start(ctx: WorkflowContext, tool: str, count: int) -> float:
    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool=tool, files_count=count),
        )
    return time.time()


def _emit_done(ctx: WorkflowContext, tool: str, start: float, count: int) -> None:
    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool=tool,
                findings_count=count,
                duration_ms=int((time.time() - start) * 1000),
            ),
        )


async def build_check(ctx: WorkflowContext) -> dict[str, BuildCheckResult]:
    """Try importing all top-level modules to verify the project loads."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    modules: set[str] = set()
    for f in files:
        parts = Path(f).parts
        if len(parts) >= 1:
            top = parts[0]
            if top.endswith(".py"):
                top = top[:-3]
            init_path = cwd / top / "__init__.py"
            standalone = cwd / f"{top}.py"
            if init_path.exists() or standalone.exists():
                modules.add(top)

    t = _emit_start(ctx, "build_check", len(modules))

    loadable: list[str] = []
    broken: list[str] = []
    errors: dict[str, str] = {}

    for mod in sorted(modules):
        result = subprocess.run(
            [PYTHON, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode == 0:
            loadable.append(mod)
        else:
            broken.append(mod)
            errors[mod] = (result.stderr or result.stdout).strip()[:500]

    _emit_done(ctx, "build_check", t, len(broken))

    return {
        "build_check": BuildCheckResult(loadable=loadable, broken=broken, errors=errors)
    }


async def dependency_health(ctx: WorkflowContext) -> dict[str, DependencyHealthResult]:
    """Check for unused deps, missing lock file, and outdated packages."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    t = _emit_start(ctx, "dependency_health", len(files))

    imported_packages: set[str] = set()
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_packages.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_packages.add(node.module.split(".")[0])

    pip_list = subprocess.run(
        [PYTHON, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    installed_names: set[str] = set()
    if pip_list.returncode == 0 and pip_list.stdout.strip():
        try:
            for pkg in json.loads(pip_list.stdout):
                installed_names.add(pkg["name"].lower().replace("-", "_"))
        except (json.JSONDecodeError, KeyError):
            pass

    stdlib = (
        set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
    )

    imported_normalized = {p.lower().replace("-", "_") for p in imported_packages}
    unused = sorted(
        name
        for name in installed_names
        if name not in imported_normalized
        and name not in stdlib
        and not name.startswith("_")
    )

    lock_files = ["uv.lock", "poetry.lock"]
    has_lock = any((cwd / lf).exists() for lf in lock_files)
    req_path = cwd / "requirements.txt"
    if not has_lock and req_path.exists():
        content = req_path.read_text()
        has_lock = "==" in content

    outdated_result = subprocess.run(
        [PYTHON, "-m", "pip", "list", "--outdated", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    outdated: list[OutdatedPackage] = []
    if outdated_result.returncode == 0 and outdated_result.stdout.strip():
        try:
            for pkg in json.loads(outdated_result.stdout):
                outdated.append(
                    OutdatedPackage(
                        name=pkg["name"],
                        current=pkg.get("version", ""),
                        latest=pkg.get("latest_version", ""),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            pass

    findings_count = len(unused) + len(outdated) + (1 if not has_lock else 0)
    _emit_done(ctx, "dependency_health", t, findings_count)

    return {
        "dependency_health": DependencyHealthResult(
            unused=unused,
            missing_lockfile=not has_lock,
            outdated=outdated,
        )
    }


async def coverage_measurement(ctx: WorkflowContext) -> dict[str, CoverageResult]:
    """Run pytest --cov, parse coverage.json, and identify under-covered files."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]
    threshold: float = getattr(ctx.config, "coverage_threshold", 40.0)

    t = _emit_start(ctx, "coverage", len(files))

    cov_json_path = cwd / "coverage.json"

    subprocess.run(
        [PYTHON, "-m", "pytest", "--cov", "--cov-report=json", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not cov_json_path.exists():
        _emit_done(ctx, "coverage", t, len(files))
        return {
            "coverage": CoverageResult(
                overall_percent=0.0,
                per_file={},
                uncovered_files=list(files),
            )
        }

    try:
        raw = json.loads(cov_json_path.read_text())
    except json.JSONDecodeError:
        _emit_done(ctx, "coverage", t, len(files))
        return {
            "coverage": CoverageResult(
                overall_percent=0.0,
                per_file={},
                uncovered_files=list(files),
            )
        }

    overall = raw.get("totals", {}).get("percent_covered", 0.0)
    per_file: dict[str, FileCoverage] = {}
    uncovered: list[str] = []

    raw_files = raw.get("files", {})
    for f in files:
        file_data = raw_files.get(f)
        if not file_data:
            uncovered.append(f)
            continue
        summary = file_data.get("summary", {})
        fc = FileCoverage(
            lines_covered=summary.get("covered_lines", 0),
            lines_missed=summary.get("missing_lines", 0),
            percent=summary.get("percent_covered", 0.0),
        )
        per_file[f] = fc
        if fc.percent < threshold:
            uncovered.append(f)

    _emit_done(ctx, "coverage", t, len(uncovered))

    return {
        "coverage": CoverageResult(
            overall_percent=overall,
            per_file=per_file,
            uncovered_files=uncovered,
        )
    }
