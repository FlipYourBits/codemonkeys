"""Discovery phase functions — file collection and metadata for each review mode."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.plans import FeaturePlan
from codemonkeys.core.analysis import analyze_files, format_analysis
from codemonkeys.workflows.phases import WorkflowContext

VENDORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", ".tox", "dist", ".eggs", "node_modules", ".git"}
)


async def discover_all_files(ctx: WorkflowContext) -> dict[str, Any]:
    """Full repo mode — find all Python files, compute AST metadata and hot file scores."""
    cwd = Path(ctx.cwd)

    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        files = [
            f
            for f in result.stdout.strip().splitlines()
            if f.endswith(".py")
            and not any(part in Path(f).parts for part in VENDORED_DIRS)
        ]
    else:
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(part in p.parts for part in VENDORED_DIRS)
        ]

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)
    hot_files = _compute_hot_files(files, analyses, cwd)

    return {
        "files": files,
        "structural_metadata": structural_metadata,
        "hot_files": hot_files,
    }


async def discover_diff(ctx: WorkflowContext) -> dict[str, Any]:
    """Diff mode — find changed files, extract diff hunks and call graph."""
    cwd = Path(ctx.cwd)
    base = ctx.config.base_branch

    name_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    files = [
        f
        for f in (
            name_result.stdout.strip().splitlines()
            if name_result.returncode == 0
            else []
        )
        if f.endswith(".py")
    ]

    stat_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--stat"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_stat = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

    hunks_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--"] + files,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_hunks = hunks_result.stdout if hunks_result.returncode == 0 else ""

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)
    call_graph = _build_call_graph(analyses)

    return {
        "files": files,
        "diff_stat": diff_stat,
        "diff_hunks": diff_hunks,
        "structural_metadata": structural_metadata,
        "call_graph": call_graph,
    }


async def discover_files(ctx: WorkflowContext) -> dict[str, Any]:
    """Files mode — use user-specified files, validate they exist."""
    cwd = Path(ctx.cwd)
    target = ctx.config.target_files or []

    files = [f for f in target if (cwd / f).exists()]

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)

    return {
        "files": files,
        "structural_metadata": structural_metadata,
    }


async def discover_from_spec(ctx: WorkflowContext) -> dict[str, Any]:
    """Post-feature mode — read spec, find implementation files, detect unplanned changes."""
    cwd = Path(ctx.cwd)

    if not ctx.config.spec_path:
        raise ValueError("spec_path is required for post_feature mode")

    spec_path = Path(ctx.config.spec_path)
    if not spec_path.is_absolute():
        spec_path = cwd / spec_path
    spec = FeaturePlan.model_validate_json(spec_path.read_text())

    spec_files: set[str] = set()
    for step in spec.steps:
        spec_files.update(f for f in step.files if f.endswith(".py"))

    diff_result = subprocess.run(
        [
            "git",
            "diff",
            f"{ctx.config.base_branch}...HEAD",
            "--name-only",
            "--diff-filter=ACMR",
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_files = set(
        f
        for f in (
            diff_result.stdout.strip().splitlines()
            if diff_result.returncode == 0
            else []
        )
        if f.endswith(".py")
    )

    all_files = sorted(spec_files | diff_files)
    unplanned = sorted(diff_files - spec_files)

    analyses = analyze_files(all_files, root=cwd)
    structural_metadata = format_analysis(analyses)

    return {
        "files": all_files,
        "spec": spec,
        "structural_metadata": structural_metadata,
        "spec_files": sorted(spec_files),
        "unplanned_files": unplanned,
    }


def _compute_hot_files(
    files: list[str],
    analyses: list,
    cwd: Path,
) -> list[dict[str, Any]]:
    """Cross-reference git churn with import fanout to find high-risk files."""
    result = subprocess.run(
        ["git", "log", "--format=", "--name-only", "--since=6 months ago"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    churn: dict[str, int] = {}
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                churn[line] = churn.get(line, 0) + 1

    import_counts: dict[str, int] = {}
    for analysis in analyses:
        for imp in analysis.imports:
            module = imp.get("module", "") or ""
            for f in files:
                stem = f.replace("/", ".").removesuffix(".py")
                if module.startswith(stem) or stem.endswith(module):
                    import_counts[f] = import_counts.get(f, 0) + 1

    hot = []
    for f in files:
        c = churn.get(f, 0)
        i = import_counts.get(f, 0)
        if c > 0 or i > 0:
            hot.append({"file": f, "churn": c, "importers": i, "score": c * (i + 1)})

    hot.sort(key=lambda h: h["score"], reverse=True)
    return hot[:20]


def _build_call_graph(analyses: list) -> str:
    """Build a simple call graph showing functions defined in changed files."""
    defined: dict[str, list[str]] = {}
    for analysis in analyses:
        names = [fn.name for fn in analysis.functions]
        names.extend(cls.name for cls in analysis.classes)
        if names:
            defined[analysis.file] = names

    if not defined:
        return "(no functions found in changed files)"

    lines = []
    for file, names in defined.items():
        lines.append(f"### `{file}` defines: {', '.join(names)}")

    return "\n".join(lines)
