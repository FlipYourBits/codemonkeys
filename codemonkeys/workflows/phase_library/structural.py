"""Structural analysis phase — import graph, cycle detection, complexity metrics."""

from __future__ import annotations

import ast
import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.refactor import CharTestResult
from codemonkeys.core.agents.python_characterization_tester import (
    make_python_characterization_tester,
)
from codemonkeys.core.runner import AgentRunner
from codemonkeys.artifacts.schemas.structural import (
    FileMetrics,
    HotFile,
    LayerViolation,
    NamingIssue,
    StructuralReport,
)
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


def _build_import_graph(files: list[str], cwd: Path) -> dict[str, list[str]]:
    """Parse AST imports for each file, resolving to file paths within the project."""
    module_to_file: dict[str, str] = {}
    for f in files:
        parts = Path(f).with_suffix("").parts
        module_to_file[".".join(parts)] = f
        if len(parts) == 1:
            module_to_file[parts[0]] = f

    graph: dict[str, list[str]] = {}
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            graph[f] = []
            continue

        imports: list[str] = []
        for node in ast.walk(tree):
            mod_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module

            if mod_name:
                top = mod_name.split(".")[0]
                resolved = module_to_file.get(mod_name) or module_to_file.get(top)
                if resolved and resolved != f:
                    imports.append(resolved)

        graph[f] = sorted(set(imports))

    return graph


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Find strongly connected components using Tarjan's algorithm."""
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for neighbor in graph.get(node, []):
            if neighbor not in index:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif on_stack.get(neighbor, False):
                lowlink[node] = min(lowlink[node], index[neighbor])

        if lowlink[node] == index[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(sorted(scc))

    for node in graph:
        if node not in index:
            strongconnect(node)

    return sccs


def _compute_file_metrics(files: list[str], cwd: Path) -> dict[str, FileMetrics]:
    """Compute line count, function/class counts, and max function length per file."""
    metrics: dict[str, FileMetrics] = {}
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue

        lines = len(source.splitlines())
        func_count = 0
        class_count = 0
        max_func_len = 0

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_count += 1
                func_len = (node.end_lineno or node.lineno) - node.lineno + 1
                max_func_len = max(max_func_len, func_len)
            elif isinstance(node, ast.ClassDef):
                class_count += 1

        metrics[f] = FileMetrics(
            lines=lines,
            function_count=func_count,
            class_count=class_count,
            max_function_length=max_func_len,
        )

    return metrics


def _detect_naming_issues(files: list[str], cwd: Path) -> list[NamingIssue]:
    """Find top-level identifiers that don't follow snake_case convention."""
    issues: list[NamingIssue] = []
    camel_re = re.compile(r"[a-z][A-Z]")

    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if camel_re.search(node.name) and not node.name.startswith("_"):
                    snake = re.sub(r"([A-Z])", r"_\1", node.name).lower().lstrip("_")
                    issues.append(
                        NamingIssue(
                            file=f,
                            name=node.name,
                            expected_convention="snake_case",
                            suggestion=snake,
                        )
                    )

    return issues


def _compute_hot_files(
    files: list[str], import_graph: dict[str, list[str]], cwd: Path
) -> list[HotFile]:
    """Score files by git churn * import fanout."""
    importer_count: dict[str, int] = {f: 0 for f in files}
    for _src, targets in import_graph.items():
        for t in targets:
            if t in importer_count:
                importer_count[t] += 1

    churn: dict[str, int] = {}
    result = subprocess.run(
        ["git", "log", "--format=%H"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        commits = result.stdout.strip().splitlines()[:200]
        for commit in commits:
            diff_result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            if diff_result.returncode == 0:
                for f in diff_result.stdout.strip().splitlines():
                    if f in importer_count:
                        churn[f] = churn.get(f, 0) + 1

    hot: list[HotFile] = []
    for f in files:
        c = churn.get(f, 0)
        i = importer_count.get(f, 0)
        if c > 0 or i > 0:
            hot.append(HotFile(file=f, churn=c, importers=i, risk_score=c * max(i, 1)))

    return sorted(hot, key=lambda h: h.risk_score, reverse=True)


def _build_test_source_map(coverage_result: object) -> dict[str, list[str]]:
    """Build test->source mapping from coverage data using naming convention."""
    per_file = getattr(coverage_result, "per_file", {})
    test_map: dict[str, list[str]] = {}

    test_files = [f for f in per_file if "test" in Path(f).name.lower()]
    source_files = [f for f in per_file if "test" not in Path(f).name.lower()]

    for tf in test_files:
        stem = Path(tf).stem
        if stem.startswith("test_"):
            src_stem = stem[5:]
        else:
            continue
        matched = [sf for sf in source_files if Path(sf).stem == src_stem]
        if matched:
            test_map[tf] = matched

    return test_map


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
            log_name=f"char_test__{batch_files[0]}",
        )

        if result.structured:
            return CharTestResult.model_validate(result.structured)
        return CharTestResult(
            tests_written=[], files_covered=batch_files, coverage_after=None
        )


async def characterization_tests(
    ctx: WorkflowContext,
) -> dict[str, list[CharTestResult]]:
    """Dispatch characterization test writers for uncovered files."""
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
