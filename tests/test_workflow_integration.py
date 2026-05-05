"""Integration smoke test — runs a full workflow with mocked agents."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.workflows.compositions import ReviewConfig, make_files_workflow
from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType
from codemonkeys.workflows.phases import WorkflowContext


def _mock_runner():
    """Create a mock AgentRunner that returns empty findings."""
    runner = MagicMock()
    runner.run_agent = AsyncMock(return_value="{}")
    runner.last_result = MagicMock(
        structured_output=FileFindings(
            file="a.py", summary="test module", findings=[]
        ).model_dump()
    )
    return runner


class TestFilesWorkflowIntegration:
    @pytest.mark.asyncio
    async def test_full_run_completes(self, tmp_path: Path) -> None:
        """Run the files workflow end-to-end with auto_fix and verify it completes."""
        (tmp_path / "a.py").write_text("x = 1\n")

        workflow = make_files_workflow(auto_fix=True)
        config = ReviewConfig(mode="files", target_files=["a.py"], auto_fix=True)
        ctx = WorkflowContext(cwd=str(tmp_path), run_id="test/run1", config=config)

        emitter = EventEmitter()
        events: list[EventType] = []
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.action.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.mechanical.subprocess"
            ) as mock_mech_sub,
            patch(
                "codemonkeys.workflows.phase_library.action.subprocess"
            ) as mock_action_sub,
        ):
            mock_mech_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            mock_action_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await engine.run(workflow, ctx)

        assert EventType.WORKFLOW_COMPLETED in events
        assert "summary" in ctx.phase_results.get("report", {})

    @pytest.mark.asyncio
    async def test_emits_phase_events_for_each_phase(self, tmp_path: Path) -> None:
        """Verify that phase started/completed events fire for every phase."""
        (tmp_path / "a.py").write_text("x = 1\n")

        workflow = make_files_workflow(auto_fix=True)
        config = ReviewConfig(mode="files", target_files=["a.py"], auto_fix=True)
        ctx = WorkflowContext(cwd=str(tmp_path), run_id="test/run1", config=config)

        emitter = EventEmitter()
        events: list[EventType] = []
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.action.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.mechanical.subprocess"
            ) as mock_mech_sub,
            patch(
                "codemonkeys.workflows.phase_library.action.subprocess"
            ) as mock_action_sub,
        ):
            mock_mech_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            mock_action_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await engine.run(workflow, ctx)

        phase_started_count = events.count(EventType.PHASE_STARTED)
        phase_completed_count = events.count(EventType.PHASE_COMPLETED)
        # FilesWorkflow has 7 phases: discover, mechanical_audit, file_review, triage, fix, verify, report
        assert phase_started_count == 7
        assert phase_completed_count == 7

    @pytest.mark.asyncio
    async def test_phase_results_chain_correctly(self, tmp_path: Path) -> None:
        """Verify that each phase can read results from prior phases."""
        (tmp_path / "a.py").write_text("def hello(): pass\n")

        workflow = make_files_workflow(auto_fix=True)
        config = ReviewConfig(mode="files", target_files=["a.py"], auto_fix=True)
        ctx = WorkflowContext(cwd=str(tmp_path), run_id="test/run1", config=config)

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.action.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.mechanical.subprocess"
            ) as mock_mech_sub,
            patch(
                "codemonkeys.workflows.phase_library.action.subprocess"
            ) as mock_action_sub,
        ):
            mock_mech_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            mock_action_sub.run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await engine.run(workflow, ctx)

        # Verify phase results populated
        assert "files" in ctx.phase_results["discover"]
        assert "a.py" in ctx.phase_results["discover"]["files"]
        assert "mechanical" in ctx.phase_results["mechanical_audit"]
        assert "file_findings" in ctx.phase_results["file_review"]
        assert "fix_requests" in ctx.phase_results["triage"]
        assert "fix_results" in ctx.phase_results["fix"]
        assert "verification" in ctx.phase_results["verify"]
        assert "summary" in ctx.phase_results["report"]
