"""Structural analysis phase — import graph, cycle detection, complexity metrics."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.refactor import CharTestResult
from codemonkeys.artifacts.schemas.structural import (
    LayerViolation,
    StructuralReport,
)
from codemonkeys.core.agents.python_characterization_tester import (
    make_python_characterization_tester,
)
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext
from codemonkeys.workflows.phase_library._structural_helpers import (
    _build_import_graph,
    _build_test_source_map,
    _compute_file_metrics,
    _compute_hot_files,
    _detect_naming_issues,
    _find_cycles,
)


async def structural_analysis(ctx: WorkflowContext) -> dict[str, StructuralReport]:
    """Build the StructuralReport: import graph, cycles, metrics, naming, hot files."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(
                tool="structural_analysis", files_count=len(files)
            ),
        )
    start = time.time()

    import_graph = _build_import_graph(files, cwd)
    circular_deps = _find_cycles(import_graph)
    file_metrics = _compute_file_metrics(files, cwd)
    naming_issues = _detect_naming_issues(files, cwd)
    hot_files = _compute_hot_files(files, import_graph, cwd)

    layer_rules: dict[str, list[str]] = getattr(ctx.config, "layer_rules", None) or {}
    layer_violations: list[LayerViolation] = []
    for src_file, targets in import_graph.items():
        for rule_module, forbidden in layer_rules.items():
            if rule_module in src_file:
                for target in targets:
                    for forbidden_mod in forbidden:
                        if forbidden_mod in target:
                            layer_violations.append(
                                LayerViolation(
                                    source_file=src_file,
                                    target_file=target,
                                    rule=f"{rule_module} cannot import from {forbidden_mod}",
                                )
                            )

    coverage_result = ctx.phase_results.get("coverage", {}).get("coverage")
    test_source_map = _build_test_source_map(coverage_result) if coverage_result else {}

    findings_count = len(circular_deps) + len(layer_violations) + len(naming_issues)

    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool="structural_analysis",
                findings_count=findings_count,
                duration_ms=int((time.time() - start) * 1000),
            ),
        )

    return {
        "structural_report": StructuralReport(
            import_graph=import_graph,
            circular_deps=circular_deps,
            file_metrics=file_metrics,
            layer_violations=layer_violations,
            naming_issues=naming_issues,
            test_source_map=test_source_map,
            hot_files=hot_files,
        )
    }


async def _run_char_test_batch(
    batch_files: list[str],
    import_graph: dict[str, list[str]],
    uncovered_lines: dict[str, list[int]],
    ctx: WorkflowContext,
    semaphore: asyncio.Semaphore,
) -> CharTestResult:
    """Dispatch a characterization tester agent for a batch of files."""
    async with semaphore:
        import_strs = []
        for f in batch_files:
            deps = import_graph.get(f, [])
            if deps:
                import_strs.append(f"{f} imports: {', '.join(deps)}")
        import_context = "\n".join(import_strs)

        batch_uncovered = {f: uncovered_lines.get(f, []) for f in batch_files}

        agent = make_python_characterization_tester(
            files=batch_files,
            import_context=import_context,
            uncovered_lines=batch_uncovered,
        )

        runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
        output_format: dict[str, Any] = {
            "type": "json_schema",
            "schema": CharTestResult.model_json_schema(),
        }
        result = await runner.run_agent(
            agent,
            f"Write characterization tests for: {', '.join(batch_files)}",
            output_format=output_format,
            agent_name="python_characterization_tester",
            files=batch_files[0],
        )

        if result.structured:
            return CharTestResult.model_validate(result.structured)
        return CharTestResult(
            tests_written=[], files_covered=batch_files, coverage_after=None
        )


_log = logging.getLogger(__name__)


def _pytest_available() -> bool:
    """Check that pytest is importable from the current Python."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


async def characterization_tests(
    ctx: WorkflowContext,
) -> dict[str, list[CharTestResult]]:
    """Dispatch characterization test writers for uncovered files."""
    if not _pytest_available():
        _log.warning(
            "pytest not installed — skipping characterization tests. "
            "Install with: uv pip install pytest"
        )
        return {"char_test_results": []}

    coverage_result = ctx.phase_results.get("coverage", {}).get("coverage")
    if not coverage_result:
        return {"char_test_results": []}

    uncovered_files: list[str] = coverage_result.uncovered_files
    if not uncovered_files:
        return {"char_test_results": []}

    structural_report = ctx.phase_results.get("structural_analysis", {}).get(
        "structural_report"
    )
    import_graph: dict[str, list[str]] = (
        structural_report.import_graph if structural_report else {}
    )

    uncovered_lines: dict[str, list[int]] = {}
    for f in uncovered_files:
        file_cov = coverage_result.per_file.get(f)
        if file_cov:
            uncovered_lines[f] = []

    batches: list[list[str]] = []
    current_batch: list[str] = []
    for f in uncovered_files:
        current_batch.append(f)
        if len(current_batch) == 3:
            batches.append(current_batch)
            current_batch = []
    if current_batch:
        batches.append(current_batch)

    config = ctx.config
    max_concurrent = getattr(config, "max_concurrent", 5)
    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = [
        _run_char_test_batch(batch, import_graph, uncovered_lines, ctx, semaphore)
        for batch in batches
    ]
    results = await asyncio.gather(*tasks)

    return {"char_test_results": list(results)}
