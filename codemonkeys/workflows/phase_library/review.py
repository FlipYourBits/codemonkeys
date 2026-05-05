"""Agent phases — dispatch reviewer agents and collect structured findings."""

from __future__ import annotations

import json
from typing import Any

from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings
from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings
from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer
from codemonkeys.core.agents.spec_compliance_reviewer import (
    make_spec_compliance_reviewer,
)
from codemonkeys.core.prompts import DIFF_CONTEXT_TEMPLATE, HARDENING_CHECKLIST
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext


async def file_review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    """Batch files, dispatch per-file reviewers (haiku for tests, sonnet for prod)."""
    files: list[str] = ctx.phase_results["discover"]["files"]
    config = ctx.config
    runner = AgentRunner(cwd=ctx.cwd)

    # Batch: up to 3 files per agent, test files on haiku, prod on sonnet
    batches: list[tuple[list[str], str]] = []
    test_batch: list[str] = []
    prod_batch: list[str] = []

    for f in files:
        if "test" in f.split("/")[-1]:
            test_batch.append(f)
            if len(test_batch) == 3:
                batches.append((test_batch, "haiku"))
                test_batch = []
        else:
            prod_batch.append(f)
            if len(prod_batch) == 3:
                batches.append((prod_batch, "sonnet"))
                prod_batch = []

    if test_batch:
        batches.append((test_batch, "haiku"))
    if prod_batch:
        batches.append((prod_batch, "sonnet"))

    all_findings: list[FileFindings] = []

    for batch_files, model in batches:
        agent = make_python_file_reviewer(batch_files, model=model)

        prompt = f"Review: {', '.join(batch_files)}"
        if config.mode == "diff":
            diff_hunks = ctx.phase_results["discover"].get("diff_hunks", "")
            call_graph = ctx.phase_results["discover"].get("call_graph", "")
            prompt = (
                DIFF_CONTEXT_TEMPLATE.format(
                    diff_hunks=diff_hunks, call_graph=call_graph
                )
                + f"\n\nReview: {', '.join(batch_files)}"
            )

        output_format: dict[str, Any] = {
            "type": "json_schema",
            "schema": FileFindings.model_json_schema(),
        }
        raw = await runner.run_agent(agent, prompt, output_format=output_format)

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
                    file=batch_files[0], summary="Could not parse output", findings=[]
                )
        all_findings.append(findings)

    return {"file_findings": all_findings}


async def architecture_review(ctx: WorkflowContext) -> dict[str, ArchitectureFindings]:
    """Dispatch architecture reviewer with mode-aware prompt enrichment."""
    files: list[str] = ctx.phase_results["discover"]["files"]
    structural_metadata: str = ctx.phase_results["discover"]["structural_metadata"]
    file_findings: list[FileFindings] = ctx.phase_results.get("file_review", {}).get(
        "file_findings", []
    )
    config = ctx.config

    file_summaries = [{"file": f.file, "summary": f.summary} for f in file_findings]

    agent = make_architecture_reviewer(
        files=files,
        file_summaries=file_summaries,
        structural_metadata=structural_metadata,
    )

    prompt = "Review the codebase for cross-file design issues."
    if config.mode == "post_feature":
        prompt += f"\n\n{HARDENING_CHECKLIST}"
    elif config.mode == "full_repo":
        hot_files = ctx.phase_results["discover"].get("hot_files", [])
        if hot_files:
            hot_text = "\n".join(
                f"- `{h['file']}` (churn: {h['churn']}, importers: {h['importers']})"
                for h in hot_files[:10]
            )
            prompt += f"\n\n## Hot Files (high churn + high fanout)\n\n{hot_text}"
    elif config.mode == "diff":
        prompt += "\n\nFocus on module boundaries touched by the diff."

    runner = AgentRunner(cwd=ctx.cwd)
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": ArchitectureFindings.model_json_schema(),
    }
    raw = await runner.run_agent(agent, prompt, output_format=output_format)

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

    return {"architecture_findings": findings}


async def doc_review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    """Dispatch readme and changelog reviewers."""
    runner = AgentRunner(cwd=ctx.cwd)
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": FileFindings.model_json_schema(),
    }
    all_findings: list[FileFindings] = []

    for make_fn, target in [
        (make_readme_reviewer, "README.md"),
        (make_changelog_reviewer, "CHANGELOG.md"),
    ]:
        agent = make_fn()
        raw = await runner.run_agent(
            agent, f"Review {target}", output_format=output_format
        )
        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            all_findings.append(FileFindings.model_validate(structured))
        else:
            try:
                all_findings.append(FileFindings.model_validate_json(raw))
            except Exception:
                all_findings.append(
                    FileFindings(file=target, summary="Could not parse", findings=[])
                )

    return {"doc_findings": all_findings}


async def spec_compliance_review(
    ctx: WorkflowContext,
) -> dict[str, SpecComplianceFindings]:
    """Dispatch spec compliance reviewer with plan and implementation files."""
    discover = ctx.phase_results["discover"]
    spec = discover["spec"]
    files = discover["files"]
    unplanned = discover.get("unplanned_files", [])

    agent = make_spec_compliance_reviewer(
        spec=spec, files=files, unplanned_files=unplanned
    )
    runner = AgentRunner(cwd=ctx.cwd)
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": SpecComplianceFindings.model_json_schema(),
    }
    raw = await runner.run_agent(
        agent,
        f"Review implementation against spec: {spec.title}",
        output_format=output_format,
    )

    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        findings = SpecComplianceFindings.model_validate(structured)
    else:
        try:
            findings = SpecComplianceFindings.model_validate_json(raw)
        except Exception:
            findings = SpecComplianceFindings(
                spec_title=spec.title,
                steps_implemented=0,
                steps_total=len(spec.steps),
                findings=[],
            )

    return {"spec_findings": findings}
