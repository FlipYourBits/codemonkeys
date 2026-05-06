from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.core.run_result import RunResult
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
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="a.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
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

    @pytest.mark.asyncio
    async def test_passes_resilience_in_full_repo_mode(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="full_repo",
            phase_results={
                "discover": {"files": ["app.py"], "structural_metadata": ""}
            },
        )

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=mock_runner,
            ),
            patch(
                "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
            ) as mock_make,
        ):
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        mock_make.assert_called_once()
        _, kwargs = mock_make.call_args
        assert kwargs.get("resilience") is True

    @pytest.mark.asyncio
    async def test_no_resilience_in_diff_mode(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="diff",
            phase_results={
                "discover": {
                    "files": ["app.py"],
                    "structural_metadata": "",
                    "diff_hunks": "",
                    "call_graph": "",
                },
            },
        )

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=mock_runner,
            ),
            patch(
                "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
            ) as mock_make,
        ):
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        _, kwargs = mock_make.call_args
        assert kwargs.get("resilience") is False

    @pytest.mark.asyncio
    async def test_passes_test_quality_for_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="test_app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="files",
            phase_results={
                "discover": {"files": ["test_app.py"], "structural_metadata": ""},
            },
        )

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=mock_runner,
            ),
            patch(
                "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
            ) as mock_make,
        ):
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        _, kwargs = mock_make.call_args
        assert kwargs.get("test_quality") is True


class TestArchitectureReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import architecture_review

        from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=ArchitectureFindings(
                    files_reviewed=["a.py"], findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
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
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured={"files_reviewed": [], "findings": []},
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
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
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="README.md", summary="readme", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(tmp_path, phase_results={"discover": {"files": ["a.py"]}})

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await doc_review(ctx)

        assert "doc_findings" in result
        assert mock_runner.run_agent.call_count == 2


class TestFileReviewerPromptInjection:
    def test_resilience_flag_injects_prompt(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["app.py"], resilience=True)
        assert "concurrency" in agent.prompt
        assert "error_recovery" in agent.prompt
        assert "log_hygiene" in agent.prompt

    def test_resilience_off_by_default(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["app.py"])
        assert "Resilience Review" not in agent.prompt

    def test_test_quality_flag_injects_prompt(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["test_app.py"], test_quality=True)
        assert "assertion_quality" in agent.prompt
        assert "test_design" in agent.prompt
        assert "isolation" in agent.prompt

    def test_test_quality_off_by_default(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["test_app.py"])
        assert "Test Quality" not in agent.prompt


class TestSpecComplianceReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import spec_compliance_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured={
                    "spec_title": "Test",
                    "steps_implemented": 1,
                    "steps_total": 1,
                    "findings": [],
                },
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
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
