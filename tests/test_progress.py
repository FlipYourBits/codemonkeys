"""Tests for workflow progress display."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    TriageReadyPayload,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext
from codemonkeys.workflows.progress import WorkflowProgress


def _make_workflow() -> Workflow:
    async def noop(ctx: WorkflowContext) -> dict:
        return {}

    return Workflow(
        name="test",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(
                name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=noop
            ),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="triage", phase_type=PhaseType.GATE, execute=noop),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=noop),
        ],
    )


class TestWorkflowProgress:
    def test_initial_state_all_pending(self) -> None:
        wf = _make_workflow()
        progress = WorkflowProgress(wf)
        assert all(s == "pending" for s in progress._phase_status.values())

    def test_phase_started_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        progress = WorkflowProgress(wf)
        progress.attach(emitter)

        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        assert progress._phase_status["discover"] == "running"

    def test_phase_completed_updates_status(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        progress = WorkflowProgress(wf)
        progress.attach(emitter)

        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )
        emitter.emit(
            EventType.PHASE_COMPLETED,
            PhaseCompletedPayload(phase="discover", workflow="test"),
        )
        assert progress._phase_status["discover"] == "done"

    def test_mechanical_tool_tracking(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        progress = WorkflowProgress(wf)
        progress.attach(emitter)

        emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool="ruff", files_count=10),
        )
        assert progress._current_tool == "ruff"

        emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool="ruff", findings_count=3, duration_ms=150
            ),
        )
        assert progress._current_tool is None
        assert len(progress._mechanical_tools) == 1
        assert progress._mechanical_tools[0]["tool"] == "ruff"
        assert progress._mechanical_tools[0]["findings"] == 3

    def test_triage_info(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        progress = WorkflowProgress(wf)
        progress.attach(emitter)

        emitter.emit(
            EventType.TRIAGE_READY,
            TriageReadyPayload(findings_count=12, fixable_count=5),
        )
        assert "12 findings" in progress._triage_info
        assert "5 fixable" in progress._triage_info

    def test_fix_progress_tracking(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        progress = WorkflowProgress(wf)
        progress.attach(emitter)

        emitter.emit(
            EventType.FIX_PROGRESS,
            FixProgressPayload(file="a.py", status="started"),
        )
        assert len(progress._fix_files) == 1
        assert progress._fix_files[0]["status"] == "started"

        emitter.emit(
            EventType.FIX_PROGRESS,
            FixProgressPayload(file="a.py", status="completed"),
        )
        assert progress._fix_files[0]["status"] == "completed"

    def test_render_produces_output(self) -> None:
        wf = _make_workflow()
        emitter = EventEmitter()
        buf = StringIO()
        c = Console(file=buf, force_terminal=True)
        progress = WorkflowProgress(wf, console=c)
        progress.attach(emitter)

        emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase="discover", workflow="test"),
        )

        rendered = progress._render()
        assert rendered is not None
