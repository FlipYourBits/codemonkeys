from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.structural import StructuralReport
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


def _make_structural_report(**overrides) -> StructuralReport:
    defaults = dict(
        import_graph={},
        circular_deps=[],
        file_metrics={},
        layer_violations=[],
        naming_issues=[],
        test_source_map={},
        hot_files=[],
    )
    defaults.update(overrides)
    return StructuralReport(**defaults)


class TestRefactorStep:
    @pytest.mark.asyncio
    async def test_skips_when_no_issues(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.refactor import refactor_step

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={
                "structural_analysis": {"structural_report": _make_structural_report()},
            },
            user_input="approve",
        )
        result = await refactor_step(ctx, step_name="refactor_circular_deps")

        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_dispatches_agent_on_approve(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.refactor import refactor_step

        report = _make_structural_report(
            circular_deps=[["a.py", "b.py"]],
        )
        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            log_dir=tmp_path / "logs",
            phase_results={
                "structural_analysis": {"structural_report": report},
            },
            user_input="approve",
        )
        (tmp_path / "logs").mkdir()

        mock_result = MagicMock()
        mock_result.structured = {
            "files_changed": ["a.py", "b.py"],
            "description": "Broke cycle",
            "tests_passed": True,
        }

        with patch(
            "codemonkeys.workflows.phase_library.refactor.AgentRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run_agent = AsyncMock(return_value=mock_result)
            result = await refactor_step(ctx, step_name="refactor_circular_deps")

        assert result["skipped"] is False
        assert result["refactor_result"].tests_passed is True


class TestFinalVerify:
    @pytest.mark.asyncio
    async def test_runs_all_checks(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.refactor import final_verify

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["foo.py"]}},
        )

        with patch(
            "codemonkeys.workflows.phase_library.refactor.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await final_verify(ctx)

        v = result["verification"]
        assert v.tests_passed is True
        assert v.lint_passed is True
        assert v.typecheck_passed is True
