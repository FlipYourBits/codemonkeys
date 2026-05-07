# tests/test_display.py
from __future__ import annotations

from codemonkeys.workflows.display import WorkflowDisplay
from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    PhaseCompletedPayload,
    PhaseStartedPayload,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def _make_workflow() -> Workflow:
    async def noop(ctx: WorkflowContext) -> dict:
        return {}

    return Workflow(
        name="test",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="triage", phase_type=PhaseType.GATE, execute=noop),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=noop),
        ],
    )


class TestWorkflowDisplayPhases:
    def test_initial_state_all_pending(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        assert all(s == "pending" for s in display._phase_status.values())

    def test_phase_started_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        assert display._phase_status["discover"] == "running"

    def test_phase_completed_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        emitter.emit(
            EventType.PHASE_COMPLETED,
            PhaseCompletedPayload(phase="discover", workflow="test"),
        )
        assert display._phase_status["discover"] == "done"


class TestWorkflowDisplayAgents:
    def test_agent_started_creates_card(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(
                agent_name="reviewer",
                task_id="r1",
                model="sonnet",
                files_label="a.py",
            ),
        )
        assert "r1" in display._agents
        assert display._agents["r1"]["model"] == "sonnet"

    def test_agent_progress_updates_tokens(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.AGENT_PROGRESS,
            AgentProgressPayload(
                agent_name="r",
                task_id="r1",
                tokens=5000,
                tool_calls=3,
                current_tool="Read(a.py)",
            ),
        )
        assert display._agents["r1"]["tokens"] == 5000
        assert display._agents["r1"]["tool_calls"] == 3

    def test_agent_completed_marks_done(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="r", task_id="r1", tokens=10000),
        )
        assert display._agents["r1"]["status"] == "done"
        assert display._agents["r1"]["tokens"] == 10000

    def test_agents_clear_on_new_phase(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(agent_name="r", task_id="r1"),
        )
        emitter.emit(
            EventType.PHASE_COMPLETED,
            PhaseCompletedPayload(phase="file_review", workflow="test"),
        )
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="triage", workflow="test"),
        )
        assert len(display._agents) == 0


class TestWorkflowDisplayCumulativeTokens:
    def test_tracks_cumulative_tokens(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="a", task_id="a1", tokens=5000),
        )
        emitter.emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(agent_name="b", task_id="b1", tokens=3000),
        )
        assert display._cumulative_tokens == 8000


class TestWorkflowDisplayMechanical:
    def test_mechanical_tool_tracking(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool="ruff", files_count=10),
        )
        assert display._current_tool == "ruff"
        emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool="ruff", findings_count=3, duration_ms=150
            ),
        )
        assert display._current_tool is None
        assert len(display._mechanical_tools) == 1


class TestWorkflowDisplayRender:
    def test_render_produces_output(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        display = WorkflowDisplay(wf, emitter)
        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        rendered = display._render()
        assert rendered is not None
