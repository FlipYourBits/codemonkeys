from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestBuildCheck:
    @pytest.mark.asyncio
    async def test_all_modules_load(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import build_check

        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("x = 1")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={
                "discover": {"files": ["mypackage/__init__.py", "mypackage/core.py"]}
            },
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await build_check(ctx)

        assert "build_check" in result
        build = result["build_check"]
        assert len(build.broken) == 0

    @pytest.mark.asyncio
    async def test_broken_module_detected(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import build_check

        broken_pkg = tmp_path / "broken"
        broken_pkg.mkdir()
        (broken_pkg / "__init__.py").write_text("")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["broken/__init__.py"]}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'missing_dep'",
            )
            result = await build_check(ctx)

        build = result["build_check"]
        assert "broken" in build.broken
        assert "missing_dep" in build.errors["broken"]

    @pytest.mark.asyncio
    async def test_emits_events(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import build_check
        from codemonkeys.workflows.events import EventEmitter, EventType

        emitter = EventEmitter()
        events: list[tuple[EventType, object]] = []
        emitter.on_any(lambda t, p: events.append((t, p)))

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["pkg/__init__.py"]}},
            emitter=emitter,
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            await build_check(ctx)

        event_types = [e[0] for e in events]
        assert EventType.MECHANICAL_TOOL_STARTED in event_types
        assert EventType.MECHANICAL_TOOL_COMPLETED in event_types


class TestDependencyHealth:
    @pytest.mark.asyncio
    async def test_detects_missing_lockfile(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import dependency_health

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": []}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            result = await dependency_health(ctx)

        assert result["dependency_health"].missing_lockfile is True

    @pytest.mark.asyncio
    async def test_detects_lockfile_present(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import dependency_health

        (tmp_path / "uv.lock").write_text("# lock")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": []}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            result = await dependency_health(ctx)

        assert result["dependency_health"].missing_lockfile is False

    @pytest.mark.asyncio
    async def test_detects_outdated_packages(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import dependency_health

        outdated_json = json.dumps(
            [
                {"name": "requests", "version": "2.25.0", "latest_version": "2.31.0"},
            ]
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["app.py"]}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=outdated_json, stderr=""
            )
            result = await dependency_health(ctx)

        assert len(result["dependency_health"].outdated) == 1
        assert result["dependency_health"].outdated[0].name == "requests"


class TestCoverageMeasurement:
    @pytest.mark.asyncio
    async def test_parses_coverage_json(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import coverage_measurement

        coverage_data = {
            "totals": {"percent_covered": 72.5},
            "files": {
                "foo.py": {
                    "summary": {
                        "covered_lines": 70,
                        "missing_lines": 30,
                        "percent_covered": 70.0,
                    }
                },
                "bar.py": {
                    "summary": {
                        "covered_lines": 10,
                        "missing_lines": 90,
                        "percent_covered": 10.0,
                    }
                },
            },
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(coverage_data))

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["foo.py", "bar.py"]}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await coverage_measurement(ctx)

        cov = result["coverage"]
        assert cov.overall_percent == 72.5
        assert cov.per_file["bar.py"].percent == 10.0
        assert "bar.py" in cov.uncovered_files
        assert "foo.py" not in cov.uncovered_files

    @pytest.mark.asyncio
    async def test_handles_pytest_failure(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import coverage_measurement

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="repo"),
            phase_results={"discover": {"files": ["foo.py"]}},
        )
        with patch(
            "codemonkeys.workflows.phase_library.stabilize.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=2, stdout="", stderr="no tests ran"
            )
            result = await coverage_measurement(ctx)

        cov = result["coverage"]
        assert cov.overall_percent == 0.0
        assert cov.uncovered_files == ["foo.py"]
