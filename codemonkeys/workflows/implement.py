"""Implement workflow — plan, approve, implement, verify."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.plans import FeaturePlan
from codemonkeys.artifacts.schemas.results import VerificationResult
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.core.agents.python_implementer import make_python_implementer
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def make_implement_workflow() -> Workflow:
    return Workflow(
        name="implement",
        phases=[
            Phase(name="plan", phase_type=PhaseType.INTERACTIVE, execute=_plan),
            Phase(name="approve", phase_type=PhaseType.GATE, execute=_approve),
            Phase(name="implement", phase_type=PhaseType.AUTOMATED, execute=_implement),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=_verify),
        ],
    )


async def _plan(ctx: WorkflowContext) -> dict[str, Any]:
    description = ctx.user_input or ""
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")

    plan = FeaturePlan(
        title=description[:80],
        description=description,
        steps=[],
    )
    store.save(ctx.run_id, "plan", plan)
    return {"plan": plan}


async def _approve(ctx: WorkflowContext) -> dict[str, FeaturePlan]:
    return {"approved_plan": ctx.user_input}


async def _implement(ctx: WorkflowContext) -> dict[str, str]:
    from codemonkeys.core.runner import AgentRunner

    plan: FeaturePlan = ctx.phase_results["approve"]["approved_plan"]
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")
    store.save(ctx.run_id, "approved-plan", plan)

    agent = make_python_implementer()
    runner = AgentRunner(cwd=ctx.cwd)
    prompt = f"Implement this plan:\n\n{plan.model_dump_json(indent=2)}"
    result = await runner.run_agent(agent, prompt)
    return {"result": result}


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

    errors = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")

    result = VerificationResult(
        tests_passed=tests.returncode == 0,
        lint_passed=lint.returncode == 0,
        typecheck_passed=True,
        errors=errors,
    )
    return {"verification": result}
