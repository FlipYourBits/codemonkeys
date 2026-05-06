from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestStructuralAnalysis:
    @pytest.mark.asyncio
    async def test_builds_import_graph(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.structural import structural_analysis

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("import c\n")
        (tmp_path / "c.py").write_text("x = 1\n")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="full_repo"),
            phase_results={
                "discover": {"files": ["a.py", "b.py", "c.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch(
            "codemonkeys.workflows.phase_library.structural.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await structural_analysis(ctx)

        report = result["structural_report"]
        assert "b.py" in report.import_graph.get("a.py", [])

    @pytest.mark.asyncio
    async def test_detects_circular_deps(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.structural import structural_analysis

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("import a\n")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="full_repo"),
            phase_results={
                "discover": {"files": ["a.py", "b.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch(
            "codemonkeys.workflows.phase_library.structural.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await structural_analysis(ctx)

        report = result["structural_report"]
        assert len(report.circular_deps) > 0

    @pytest.mark.asyncio
    async def test_computes_file_metrics(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.structural import structural_analysis

        code = "def foo():\n    pass\n\ndef bar():\n    x = 1\n    y = 2\n    return x + y\n\nclass Baz:\n    pass\n"
        (tmp_path / "mod.py").write_text(code)

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="full_repo"),
            phase_results={
                "discover": {"files": ["mod.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch(
            "codemonkeys.workflows.phase_library.structural.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await structural_analysis(ctx)

        metrics = result["structural_report"].file_metrics["mod.py"]
        assert metrics.function_count == 2
        assert metrics.class_count == 1


class TestCharacterizationTests:
    @pytest.mark.asyncio
    async def test_dispatches_agents_for_uncovered_files(self, tmp_path: Path) -> None:
        from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage
        from codemonkeys.workflows.phase_library.structural import (
            characterization_tests,
        )

        coverage = CoverageResult(
            overall_percent=30.0,
            per_file={
                "foo.py": FileCoverage(lines_covered=10, lines_missed=90, percent=10.0),
                "bar.py": FileCoverage(lines_covered=80, lines_missed=20, percent=80.0),
            },
            uncovered_files=["foo.py"],
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="full_repo"),
            log_dir=tmp_path / "logs",
            phase_results={
                "discover": {"files": ["foo.py", "bar.py"]},
                "coverage": {"coverage": coverage},
                "structural_analysis": {
                    "structural_report": MagicMock(
                        import_graph={"foo.py": [], "bar.py": []},
                    )
                },
            },
        )
        (tmp_path / "logs").mkdir()

        mock_result = MagicMock()
        mock_result.structured = {
            "tests_written": ["tests/test_foo.py"],
            "files_covered": ["foo.py"],
            "coverage_after": None,
        }

        with patch(
            "codemonkeys.workflows.phase_library.structural.AgentRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run_agent = AsyncMock(return_value=mock_result)
            result = await characterization_tests(ctx)

        assert "char_test_results" in result
        assert instance.run_agent.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_when_no_uncovered_files(self, tmp_path: Path) -> None:
        from codemonkeys.artifacts.schemas.coverage import CoverageResult
        from codemonkeys.workflows.phase_library.structural import (
            characterization_tests,
        )

        coverage = CoverageResult(
            overall_percent=95.0,
            per_file={},
            uncovered_files=[],
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="full_repo"),
            phase_results={
                "discover": {"files": []},
                "coverage": {"coverage": coverage},
                "structural_analysis": {
                    "structural_report": MagicMock(import_graph={})
                },
            },
        )
        result = await characterization_tests(ctx)

        assert result["char_test_results"] == []
