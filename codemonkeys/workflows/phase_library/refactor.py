"""Refactor phases — gated structural refactoring, README update, final verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.refactor import StructuralRefactorResult
from codemonkeys.artifacts.schemas.results import VerificationResult
from codemonkeys.artifacts.schemas.structural import StructuralReport
from codemonkeys.core.agents.python_structural_refactorer import (
    make_python_structural_refactorer,
)
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable

_STEP_TO_DATA: dict[str, str] = {
    "refactor_circular_deps": "circular_deps",
    "refactor_layering": "layer_violations",
    "refactor_god_modules": "file_metrics",
    "refactor_extract_shared": "file_metrics",
    "refactor_dead_code": "file_metrics",
    "refactor_naming": "naming_issues",
}

_STEP_TO_REFACTOR_TYPE: dict[str, str] = {
    "refactor_circular_deps": "circular_deps",
    "refactor_layering": "layering",
    "refactor_god_modules": "god_modules",
    "refactor_extract_shared": "extract_shared",
    "refactor_dead_code": "dead_code",
    "refactor_naming": "naming",
}


def _extract_issues_for_step(
    step_name: str, report: StructuralReport
) -> tuple[list[str], str]:
    """Extract affected files and problem description from the structural report."""
    refactor_type = _STEP_TO_REFACTOR_TYPE.get(step_name, "")

    if refactor_type == "circular_deps":
        if not report.circular_deps:
            return [], ""
        files: set[str] = set()
        descs: list[str] = []
        for cycle in report.circular_deps:
            files.update(cycle)
            descs.append(" -> ".join(cycle) + f" -> {cycle[0]}")
        return sorted(files), "Circular dependencies:\n" + "\n".join(descs)

    if refactor_type == "layering":
        if not report.layer_violations:
            return [], ""
        files = set()
        descs = []
        for v in report.layer_violations:
            files.add(v.source_file)
            files.add(v.target_file)
            descs.append(f"{v.source_file} imports {v.target_file} ({v.rule})")
        return sorted(files), "Layer violations:\n" + "\n".join(descs)

    if refactor_type == "god_modules":
        GOD_MODULE_THRESHOLD = 300
        big_files = [
            (f, m)
            for f, m in report.file_metrics.items()
            if m.lines > GOD_MODULE_THRESHOLD
        ]
        if not big_files:
            return [], ""
        files_list = [f for f, _ in big_files]
        descs = [
            f"{f} ({m.lines} lines, {m.function_count} functions, {m.class_count} classes)"
            for f, m in big_files
        ]
        return files_list, "Oversized modules:\n" + "\n".join(descs)

    if refactor_type == "extract_shared":
        threshold = 8
        candidates = [
            (f, m)
            for f, m in report.file_metrics.items()
            if m.function_count > threshold
        ]
        if not candidates:
            return [], ""
        files_list = [f for f, _ in candidates]
        descs = [
            f"{f} ({m.function_count} functions — check for extractable shared logic)"
            for f, m in candidates
        ]
        return files_list, "Potential duplication:\n" + "\n".join(descs)

    if refactor_type == "dead_code":
        dead_candidates = [
            h.file for h in report.hot_files if h.importers == 0 and h.churn == 0
        ]
        if not dead_candidates:
            return [], ""
        return (
            dead_candidates,
            "Potentially dead modules (0 importers, 0 churn):\n"
            + "\n".join(f"- {f}" for f in dead_candidates),
        )

    if refactor_type == "naming":
        if not report.naming_issues:
            return [], ""
        files = sorted({n.file for n in report.naming_issues})
        descs = [
            f"{n.file}: `{n.name}` -> `{n.suggestion}` ({n.expected_convention})"
            for n in report.naming_issues
        ]
        return files, "Naming inconsistencies:\n" + "\n".join(descs)

    return [], ""


async def refactor_step(
    ctx: WorkflowContext, *, step_name: str | None = None
) -> dict[str, Any]:
    """Execute a single refactoring step. Called with step_name to identify which step."""
    report: StructuralReport = ctx.phase_results["structural_analysis"][
        "structural_report"
    ]

    if not step_name:
        for name in _STEP_TO_REFACTOR_TYPE:
            if name not in ctx.phase_results:
                step_name = name
                break
        if not step_name:
            return {"skipped": True, "refactor_result": None}

    affected_files, problem_description = _extract_issues_for_step(step_name, report)

    if not affected_files:
        return {"skipped": True, "refactor_result": None}

    if (
        ctx.user_input
        and isinstance(ctx.user_input, str)
        and ctx.user_input.lower() == "skip"
    ):
        return {"skipped": True, "refactor_result": None}

    test_files: list[str] = []
    for test_file, source_files in report.test_source_map.items():
        if any(sf in affected_files for sf in source_files):
            test_files.append(test_file)

    refactor_type = _STEP_TO_REFACTOR_TYPE[step_name]
    agent = make_python_structural_refactorer(
        files=affected_files,
        problem_description=problem_description,
        refactor_type=refactor_type,
        test_files=test_files,
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": StructuralRefactorResult.model_json_schema(),
    }
    result = await runner.run_agent(
        agent,
        f"Refactor ({refactor_type}): {problem_description[:200]}",
        output_format=output_format,
        log_name=f"refactor__{step_name}",
    )

    if result.structured:
        refactor_result = StructuralRefactorResult.model_validate(result.structured)
    else:
        refactor_result = StructuralRefactorResult(
            files_changed=[],
            description="Could not parse agent output",
            tests_passed=False,
        )

    return {"skipped": False, "refactor_result": refactor_result}


async def update_readme(ctx: WorkflowContext) -> dict[str, Any]:
    """Update README.md using the refreshed StructuralReport."""
    import json

    report: StructuralReport | None = ctx.phase_results.get(
        "rescan_structure", ctx.phase_results.get("structural_analysis", {})
    ).get("structural_report")
    if not report:
        return {"readme_updated": False}

    cwd = Path(ctx.cwd)
    readme_path = cwd / "README.md"
    if not readme_path.exists():
        return {"readme_updated": False}

    from codemonkeys.core.prompts import PYTHON_CMD

    report_summary = json.dumps(
        {
            "files": sorted(report.import_graph.keys()),
            "modules": sorted({f.split("/")[0] for f in report.import_graph}),
            "file_count": len(report.import_graph),
        },
        indent=2,
    )

    from claude_agent_sdk import AgentDefinition

    agent = AgentDefinition(
        description="Update README.md to reflect refactored structure",
        prompt=f"""\
You update a project's README.md to match the current codebase structure.
You are given a structural summary showing the current files and modules.

## Structural Summary

```json
{report_summary}
```

## Method

1. Read README.md.
2. Update any file paths, module references, or structure descriptions
   that no longer match the structural summary above.
3. Do NOT change the README's tone, purpose, or non-structural content.
4. If the README is already accurate, make no changes.

## Rules

- Only update structural references. Don't rewrite prose.
- Don't add new sections. Only fix inaccuracies.
- Run `{PYTHON_CMD} -m ruff format README.md` if you changed it (skip if it's not a .py file).""",
        model="sonnet",
        tools=["Read", "Edit"],
        permissionMode="acceptEdits",
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    await runner.run_agent(agent, "Update README.md", log_name="update_readme")

    return {"readme_updated": True}


async def final_verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    """Run the full mechanical suite: pytest, ruff, pyright, import check."""
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

    errors: list[str] = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")
    if typecheck.returncode != 0:
        errors.append(f"pyright: {typecheck.stdout[:500]}")

    files: list[str] = ctx.phase_results.get("discover", {}).get("files", [])
    modules: set[str] = set()
    for f in files:
        parts = Path(f).parts
        if parts:
            modules.add(parts[0].replace(".py", ""))

    for mod in modules:
        result = subprocess.run(
            [PYTHON, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            errors.append(f"import {mod}: {result.stderr[:200]}")

    return {
        "verification": VerificationResult(
            tests_passed=tests.returncode == 0,
            lint_passed=lint.returncode == 0,
            typecheck_passed=typecheck.returncode == 0,
            errors=errors,
        )
    }
