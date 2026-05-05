from __future__ import annotations

import asyncio

import pytest

from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_runs_automated_phases(self) -> None:
        results: list[str] = []

        async def phase_a(ctx: WorkflowContext) -> dict[str, str]:
            results.append("a")
            return {"output": "from_a"}

        async def phase_b(ctx: WorkflowContext) -> dict[str, str]:
            results.append("b")
            return {"output": "from_b"}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="a", phase_type=PhaseType.AUTOMATED, execute=phase_a),
                Phase(name="b", phase_type=PhaseType.AUTOMATED, execute=phase_b),
            ],
        )

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        await engine.run(workflow, ctx)
        assert results == ["a", "b"]

    @pytest.mark.asyncio
    async def test_gate_phase_waits_for_user(self) -> None:
        async def review_phase(ctx: WorkflowContext) -> dict[str, str]:
            return {"findings": "some findings"}

        async def triage_phase(ctx: WorkflowContext) -> dict[str, list[str]]:
            return {"selected": ctx.user_input}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(
                    name="review", phase_type=PhaseType.AUTOMATED, execute=review_phase
                ),
                Phase(name="triage", phase_type=PhaseType.GATE, execute=triage_phase),
            ],
        )

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")

        async def resolve_later() -> None:
            await asyncio.sleep(0.05)
            engine.resolve_gate(["fix_item_1"])

        asyncio.get_event_loop().create_task(resolve_later())
        await engine.run(workflow, ctx)
        assert ctx.phase_results.get("triage") == {"selected": ["fix_item_1"]}

    @pytest.mark.asyncio
    async def test_emits_events(self) -> None:
        events: list[EventType] = []

        async def noop(ctx: WorkflowContext) -> dict[str, str]:
            return {}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="only", phase_type=PhaseType.AUTOMATED, execute=noop),
            ],
        )

        emitter = EventEmitter()
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        await engine.run(workflow, ctx)
        assert EventType.PHASE_STARTED in events
        assert EventType.PHASE_COMPLETED in events
        assert EventType.WORKFLOW_COMPLETED in events

    @pytest.mark.asyncio
    async def test_error_emits_error_event(self) -> None:
        events: list[EventType] = []

        async def failing(ctx: WorkflowContext) -> dict[str, str]:
            raise RuntimeError("boom")

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="fail", phase_type=PhaseType.AUTOMATED, execute=failing),
            ],
        )

        emitter = EventEmitter()
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        with pytest.raises(RuntimeError, match="boom"):
            await engine.run(workflow, ctx)
        assert EventType.WORKFLOW_ERROR in events
