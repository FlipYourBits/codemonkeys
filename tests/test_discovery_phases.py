from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestDiscoverAllFiles:
    @pytest.mark.asyncio
    async def test_finds_python_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_all_files

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        (tmp_path / "src" / "util.py").write_text("y = 2")

        with patch(
            "codemonkeys.workflows.phase_library.discovery.subprocess"
        ) as mock_sub:
            # First call: git ls-files
            ls_result = MagicMock(returncode=0, stdout="src/main.py\nsrc/util.py\n")
            # Second call: git log (for hot files)
            log_result = MagicMock(returncode=0, stdout="src/main.py\nsrc/main.py\n")
            mock_sub.run.side_effect = [ls_result, log_result]

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="repo"),
            )
            result = await discover_all_files(ctx)

        assert "src/main.py" in result["files"]
        assert "src/util.py" in result["files"]
        assert "structural_metadata" in result
        assert "hot_files" in result

    @pytest.mark.asyncio
    async def test_filters_vendored(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_all_files

        with patch(
            "codemonkeys.workflows.phase_library.discovery.subprocess"
        ) as mock_sub:
            ls_result = MagicMock(returncode=0, stdout="src/main.py\n.venv/lib/x.py\n")
            log_result = MagicMock(returncode=0, stdout="")
            mock_sub.run.side_effect = [ls_result, log_result]

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="repo"),
            )
            result = await discover_all_files(ctx)

        assert ".venv/lib/x.py" not in result["files"]


class TestDiscoverDiff:
    @pytest.mark.asyncio
    async def test_finds_changed_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_diff

        (tmp_path / "changed.py").write_text("x = 1")

        with patch(
            "codemonkeys.workflows.phase_library.discovery.subprocess"
        ) as mock_sub:
            name_result = MagicMock(returncode=0, stdout="changed.py\n")
            stat_result = MagicMock(returncode=0, stdout=" 1 file changed\n")
            hunks_result = MagicMock(
                returncode=0, stdout="diff --git a/changed.py\n+x = 1\n"
            )
            mock_sub.run.side_effect = [name_result, stat_result, hunks_result]

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="diff"),
            )
            result = await discover_diff(ctx)

        assert "changed.py" in result["files"]
        assert "diff_stat" in result
        assert "diff_hunks" in result
        assert "structural_metadata" in result
        assert "call_graph" in result


class TestDiscoverFiles:
    @pytest.mark.asyncio
    async def test_uses_target_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_files

        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["a.py", "b.py"]),
        )
        result = await discover_files(ctx)

        assert result["files"] == ["a.py", "b.py"]
        assert "structural_metadata" in result

    @pytest.mark.asyncio
    async def test_filters_missing_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_files

        (tmp_path / "a.py").write_text("x = 1")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["a.py", "missing.py"]),
        )
        result = await discover_files(ctx)

        assert "a.py" in result["files"]
        assert "missing.py" not in result["files"]


class TestDiscoverFromSpec:
    @pytest.mark.asyncio
    async def test_reads_spec_and_finds_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.discovery import discover_from_spec

        spec = FeaturePlan(
            title="Add caching",
            description="Redis caching.",
            steps=[PlanStep(description="Add cache", files=["src/cache.py"])],
        )
        spec_path = tmp_path / "plan.json"
        spec_path.write_text(spec.model_dump_json())
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "cache.py").write_text("x = 1")

        with patch(
            "codemonkeys.workflows.phase_library.discovery.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="src/cache.py\nsrc/extra.py\n"
            )

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="post_feature", spec_path=str(spec_path)),
            )
            result = await discover_from_spec(ctx)

        assert "src/cache.py" in result["files"]
        assert result["spec"].title == "Add caching"
        assert "src/cache.py" in result["spec_files"]
        assert "src/extra.py" in result["unplanned_files"]
