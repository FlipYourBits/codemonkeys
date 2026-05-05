from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


def _make_finding(file: str = "a.py", severity: str = "medium") -> Finding:
    return Finding(
        file=file,
        line=10,
        severity=severity,
        category="quality",
        subcategory="naming",
        title="Bad name",
        description="Variable has a bad name.",
        suggestion="Rename it.",
    )


def _make_ctx(tmp_path: Path, phase_results: dict, **kwargs) -> WorkflowContext:
    return WorkflowContext(
        cwd=str(tmp_path),
        run_id="test/run1",
        config=ReviewConfig(mode="full_repo", **kwargs),
        phase_results=phase_results,
    )


class TestTriage:
    @pytest.mark.asyncio
    async def test_auto_fix_selects_medium_and_above(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        ctx = _make_ctx(
            tmp_path,
            auto_fix=True,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[
                                _make_finding(severity="high"),
                                _make_finding(severity="medium"),
                                _make_finding(severity="low"),
                                _make_finding(severity="info"),
                            ],
                        )
                    ]
                },
            },
        )
        result = await triage(ctx)
        requests = result["fix_requests"]
        assert len(requests) == 1
        assert len(requests[0].findings) == 2  # high + medium only

    @pytest.mark.asyncio
    async def test_collects_from_multiple_sources(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        ctx = _make_ctx(
            tmp_path,
            auto_fix=True,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[_make_finding(file="a.py")],
                        )
                    ]
                },
                "doc_review": {
                    "doc_findings": [
                        FileFindings(
                            file="README.md",
                            summary="readme",
                            findings=[_make_finding(file="README.md")],
                        )
                    ]
                },
            },
        )
        result = await triage(ctx)
        files_in_requests = {r.file for r in result["fix_requests"]}
        assert "a.py" in files_in_requests
        assert "README.md" in files_in_requests

    @pytest.mark.asyncio
    async def test_uses_user_input_when_provided(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        manual_requests = [
            FixRequest(file="x.py", findings=[_make_finding(file="x.py")])
        ]
        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[_make_finding()],
                        )
                    ]
                },
            },
        )
        ctx.user_input = manual_requests
        result = await triage(ctx)
        assert result["fix_requests"] == manual_requests


class TestFix:
    @pytest.mark.asyncio
    async def test_dispatches_fixer_per_file(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import fix

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FixResult(
                file="a.py", fixed=["fixed"], skipped=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "triage": {
                    "fix_requests": [
                        FixRequest(file="a.py", findings=[_make_finding()]),
                        FixRequest(file="b.py", findings=[_make_finding(file="b.py")]),
                    ]
                }
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.action.AgentRunner",
            return_value=mock_runner,
        ):
            result = await fix(ctx)

        assert len(result["fix_results"]) == 2
        assert mock_runner.run_agent.call_count == 2


class TestVerify:
    @pytest.mark.asyncio
    async def test_returns_verification_result(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import verify

        with patch("codemonkeys.workflows.phase_library.action.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ctx = _make_ctx(tmp_path, phase_results={})
            result = await verify(ctx)

        assert result["verification"].tests_passed is True
        assert result["verification"].lint_passed is True
        assert result["verification"].typecheck_passed is True


class TestReport:
    @pytest.mark.asyncio
    async def test_summarizes_results(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import report

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "fix": {
                    "fix_results": [
                        FixResult(
                            file="a.py", fixed=["fix1", "fix2"], skipped=["skip1"]
                        )
                    ]
                },
                "verify": {
                    "verification": VerificationResult(
                        tests_passed=True,
                        lint_passed=True,
                        typecheck_passed=True,
                        errors=[],
                    )
                },
            },
        )
        result = await report(ctx)
        assert result["summary"]["fixed"] == 2
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["tests_passed"] is True
