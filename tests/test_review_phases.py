from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


def _make_ctx(
    tmp_path: Path, mode: str = "full_repo", phase_results: dict | None = None, **kwargs
) -> WorkflowContext:
    return WorkflowContext(
        cwd=str(tmp_path),
        run_id="test/run1",
        config=ReviewConfig(mode=mode, **kwargs),
        phase_results=phase_results or {},
    )


class TestFileReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FileFindings(
                file="a.py", summary="test", findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={"discover": {"files": ["a.py"], "structural_metadata": ""}},
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await file_review(ctx)

        assert "file_findings" in result
        assert mock_runner.run_agent.call_count >= 1


class TestArchitectureReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import architecture_review

        from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=ArchitectureFindings(
                files_reviewed=["a.py"], findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "discover": {"files": ["a.py"], "structural_metadata": "meta"},
                "file_review": {
                    "file_findings": [
                        FileFindings(file="a.py", summary="mod", findings=[])
                    ]
                },
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await architecture_review(ctx)

        assert "architecture_findings" in result

    @pytest.mark.asyncio
    async def test_post_feature_includes_hardening(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import architecture_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output={"files_reviewed": [], "findings": []}
        )

        ctx = _make_ctx(
            tmp_path,
            mode="post_feature",
            spec_path="plan.json",
            phase_results={
                "discover": {"files": ["a.py"], "structural_metadata": ""},
                "file_review": {"file_findings": []},
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            await architecture_review(ctx)

        call_args = mock_runner.run_agent.call_args
        prompt = (
            call_args[0][1]
            if len(call_args[0]) > 1
            else call_args.kwargs.get("prompt", "")
        )
        assert "error_paths" in prompt.lower() or "hardening" in prompt.lower()


class TestDocReview:
    @pytest.mark.asyncio
    async def test_dispatches_both_reviewers(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import doc_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FileFindings(
                file="README.md", summary="readme", findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(tmp_path, phase_results={"discover": {"files": ["a.py"]}})

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await doc_review(ctx)

        assert "doc_findings" in result
        assert mock_runner.run_agent.call_count == 2


class TestSpecComplianceReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import spec_compliance_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output={
                "spec_title": "Test",
                "steps_implemented": 1,
                "steps_total": 1,
                "findings": [],
            }
        )

        spec = FeaturePlan(
            title="Test",
            description="Test.",
            steps=[PlanStep(description="step", files=["a.py"])],
        )
        ctx = _make_ctx(
            tmp_path,
            mode="post_feature",
            spec_path="plan.json",
            phase_results={
                "discover": {"files": ["a.py"], "spec": spec, "unplanned_files": []},
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await spec_compliance_review(ctx)

        assert "spec_findings" in result
