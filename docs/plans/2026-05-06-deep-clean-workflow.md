# Deep Clean Workflow Implementation Plan

**Goal:** Add a `--deep-clean` CLI mode that stabilizes and structurally refactors an entire codebase through mechanical analysis, characterization test generation, and gated incremental refactoring.

**Architecture:** New mechanical phases (build_check, dependency_health, coverage_measurement, structural_analysis) feed a StructuralReport into two new agents (characterization tester, structural refactorer). The workflow is composed from reusable phase functions and wired into the existing WorkflowEngine. Refactor steps use GATE phases so the user approves each structural change.

**Tech Stack:** Python 3.12+, Pydantic, asyncio, Claude Agent SDK, pytest, ruff, pyright, coverage.py

**Spec:** `docs/specs/2026-05-05-deep-clean-workflow-design.md`

---

### Task 1: Pydantic Schemas — Health & Coverage

**Files:**
- Create: `codemonkeys/artifacts/schemas/health.py`
- Create: `codemonkeys/artifacts/schemas/coverage.py`
- Test: `tests/test_deep_clean_schemas.py`

- [ ] **Step 1: Write tests for health schemas**

```python
# tests/test_deep_clean_schemas.py
from __future__ import annotations

from codemonkeys.artifacts.schemas.health import (
    BuildCheckResult,
    DependencyHealthResult,
    OutdatedPackage,
)


class TestBuildCheckResult:
    def test_all_loadable(self) -> None:
        r = BuildCheckResult(loadable=["foo", "bar"], broken=[], errors={})
        assert len(r.loadable) == 2
        assert not r.broken

    def test_with_broken_modules(self) -> None:
        r = BuildCheckResult(
            loadable=["foo"],
            broken=["bar"],
            errors={"bar": "ModuleNotFoundError: No module named 'baz'"},
        )
        assert r.broken == ["bar"]
        assert "baz" in r.errors["bar"]


class TestDependencyHealthResult:
    def test_healthy(self) -> None:
        r = DependencyHealthResult(unused=[], missing_lockfile=False, outdated=[])
        assert not r.unused
        assert not r.missing_lockfile

    def test_with_issues(self) -> None:
        pkg = OutdatedPackage(name="requests", current="2.25.0", latest="2.31.0")
        r = DependencyHealthResult(
            unused=["flask"], missing_lockfile=True, outdated=[pkg]
        )
        assert r.unused == ["flask"]
        assert r.missing_lockfile
        assert r.outdated[0].name == "requests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deep_clean_schemas.py::TestBuildCheckResult -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'codemonkeys.artifacts.schemas.health'`

- [ ] **Step 3: Implement health schemas**

```python
# codemonkeys/artifacts/schemas/health.py
"""Schemas for build check and dependency health results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildCheckResult(BaseModel):
    loadable: list[str] = Field(description="Modules that imported successfully")
    broken: list[str] = Field(description="Modules that failed to import")
    errors: dict[str, str] = Field(description="Module name -> error message for broken modules")


class OutdatedPackage(BaseModel):
    name: str = Field(description="Package name")
    current: str = Field(description="Currently installed version")
    latest: str = Field(description="Latest available version")


class DependencyHealthResult(BaseModel):
    unused: list[str] = Field(description="Installed packages never imported in source")
    missing_lockfile: bool = Field(description="Whether uv.lock / poetry.lock / pinned requirements.txt is missing")
    outdated: list[OutdatedPackage] = Field(description="Packages with newer versions available")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deep_clean_schemas.py::TestBuildCheckResult tests/test_deep_clean_schemas.py::TestDependencyHealthResult -v`
Expected: PASS

- [ ] **Step 5: Write tests for coverage schemas**

Add to `tests/test_deep_clean_schemas.py`:

```python
from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage


class TestCoverageResult:
    def test_full_coverage(self) -> None:
        fc = FileCoverage(lines_covered=100, lines_missed=0, percent=100.0)
        r = CoverageResult(
            overall_percent=100.0,
            per_file={"foo.py": fc},
            uncovered_files=[],
        )
        assert r.overall_percent == 100.0
        assert not r.uncovered_files

    def test_partial_coverage(self) -> None:
        fc = FileCoverage(lines_covered=10, lines_missed=90, percent=10.0)
        r = CoverageResult(
            overall_percent=10.0,
            per_file={"bar.py": fc},
            uncovered_files=["bar.py"],
        )
        assert r.uncovered_files == ["bar.py"]
        assert r.per_file["bar.py"].lines_missed == 90
```

- [ ] **Step 6: Implement coverage schemas**

```python
# codemonkeys/artifacts/schemas/coverage.py
"""Schemas for real code coverage measurement results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileCoverage(BaseModel):
    lines_covered: int = Field(description="Number of executed lines")
    lines_missed: int = Field(description="Number of unexecuted lines")
    percent: float = Field(description="Line coverage percentage")


class CoverageResult(BaseModel):
    overall_percent: float = Field(description="Overall line coverage percentage")
    per_file: dict[str, FileCoverage] = Field(description="Per-file coverage breakdown")
    uncovered_files: list[str] = Field(description="Files below the coverage threshold")
```

- [ ] **Step 7: Run all schema tests**

Run: `uv run pytest tests/test_deep_clean_schemas.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add codemonkeys/artifacts/schemas/health.py codemonkeys/artifacts/schemas/coverage.py tests/test_deep_clean_schemas.py
git commit -m "feat(deep-clean): add health and coverage Pydantic schemas"
```

---

### Task 2: Pydantic Schemas — Structural & Refactor

**Files:**
- Create: `codemonkeys/artifacts/schemas/structural.py`
- Create: `codemonkeys/artifacts/schemas/refactor.py`
- Test: `tests/test_deep_clean_schemas.py` (append)

- [ ] **Step 1: Write tests for structural schemas**

Add to `tests/test_deep_clean_schemas.py`:

```python
from codemonkeys.artifacts.schemas.structural import (
    FileMetrics,
    HotFile,
    LayerViolation,
    NamingIssue,
    StructuralReport,
)


class TestStructuralReport:
    def test_empty_report(self) -> None:
        r = StructuralReport(
            import_graph={},
            circular_deps=[],
            file_metrics={},
            layer_violations=[],
            naming_issues=[],
            test_source_map={},
            hot_files=[],
        )
        assert not r.circular_deps

    def test_with_cycle(self) -> None:
        r = StructuralReport(
            import_graph={"a.py": ["b.py"], "b.py": ["a.py"]},
            circular_deps=[["a.py", "b.py"]],
            file_metrics={
                "a.py": FileMetrics(
                    lines=100, function_count=5, class_count=1, max_function_length=40
                ),
            },
            layer_violations=[
                LayerViolation(
                    source_file="utils/helpers.py",
                    target_file="workflows/engine.py",
                    rule="utils cannot import from workflows",
                )
            ],
            naming_issues=[
                NamingIssue(
                    file="core/runner.py",
                    name="runAgent",
                    expected_convention="snake_case",
                    suggestion="run_agent",
                )
            ],
            test_source_map={"tests/test_a.py": ["a.py"]},
            hot_files=[HotFile(file="a.py", churn=50, importers=10, risk_score=500)],
        )
        assert len(r.circular_deps) == 1
        assert r.hot_files[0].risk_score == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deep_clean_schemas.py::TestStructuralReport -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement structural schemas**

```python
# codemonkeys/artifacts/schemas/structural.py
"""Schemas for structural analysis — import graph, cycles, complexity, naming."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileMetrics(BaseModel):
    lines: int = Field(description="Total lines in file")
    function_count: int = Field(description="Number of top-level functions")
    class_count: int = Field(description="Number of top-level classes")
    max_function_length: int = Field(description="Length of longest function in lines")


class LayerViolation(BaseModel):
    source_file: str = Field(description="File that contains the violating import")
    target_file: str = Field(description="File being imported in violation of layer rules")
    rule: str = Field(description="The layer rule being violated")


class NamingIssue(BaseModel):
    file: str = Field(description="File containing the naming inconsistency")
    name: str = Field(description="The inconsistent identifier")
    expected_convention: str = Field(description="Convention used by the majority of the codebase")
    suggestion: str = Field(description="Suggested replacement name")


class HotFile(BaseModel):
    file: str = Field(description="File path")
    churn: int = Field(description="Number of commits touching this file")
    importers: int = Field(description="Number of other files that import this module")
    risk_score: int = Field(description="churn * importers — higher means more impactful to refactor")


class StructuralReport(BaseModel):
    import_graph: dict[str, list[str]] = Field(description="Module -> list of modules it imports")
    circular_deps: list[list[str]] = Field(description="Each cycle as an ordered list of files")
    file_metrics: dict[str, FileMetrics] = Field(description="Per-file complexity stats")
    layer_violations: list[LayerViolation] = Field(description="Import-based layer rule violations")
    naming_issues: list[NamingIssue] = Field(description="Mixed naming convention issues")
    test_source_map: dict[str, list[str]] = Field(description="test_file -> source_files it covers")
    hot_files: list[HotFile] = Field(description="Files ordered by risk score (churn * fanout)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deep_clean_schemas.py::TestStructuralReport -v`
Expected: PASS

- [ ] **Step 5: Write tests for refactor schemas**

Add to `tests/test_deep_clean_schemas.py`:

```python
from codemonkeys.artifacts.schemas.refactor import CharTestResult, StructuralRefactorResult


class TestRefactorSchemas:
    def test_char_test_result(self) -> None:
        r = CharTestResult(
            tests_written=["tests/test_foo.py"],
            files_covered=["foo.py"],
            coverage_after=85.0,
        )
        assert r.tests_written == ["tests/test_foo.py"]

    def test_char_test_result_no_coverage(self) -> None:
        r = CharTestResult(
            tests_written=["tests/test_bar.py"],
            files_covered=["bar.py"],
            coverage_after=None,
        )
        assert r.coverage_after is None

    def test_structural_refactor_result(self) -> None:
        r = StructuralRefactorResult(
            files_changed=["a.py", "b.py"],
            description="Broke circular dependency between a and b",
            tests_passed=True,
        )
        assert r.tests_passed
        assert len(r.files_changed) == 2
```

- [ ] **Step 6: Implement refactor schemas**

```python
# codemonkeys/artifacts/schemas/refactor.py
"""Schemas for refactoring and characterization test results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CharTestResult(BaseModel):
    tests_written: list[str] = Field(description="Paths to newly created test files")
    files_covered: list[str] = Field(description="Source files now covered by characterization tests")
    coverage_after: float | None = Field(description="Re-measured coverage percentage, or null")


class StructuralRefactorResult(BaseModel):
    files_changed: list[str] = Field(description="Files that were modified or created")
    description: str = Field(description="What structural change was made")
    tests_passed: bool = Field(description="Whether scoped tests passed after the change")
```

- [ ] **Step 7: Run all schema tests**

Run: `uv run pytest tests/test_deep_clean_schemas.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add codemonkeys/artifacts/schemas/structural.py codemonkeys/artifacts/schemas/refactor.py tests/test_deep_clean_schemas.py
git commit -m "feat(deep-clean): add structural and refactor Pydantic schemas"
```

---

### Task 3: Stabilize Phase — build_check

**Files:**
- Create: `codemonkeys/workflows/phase_library/stabilize.py`
- Test: `tests/test_stabilize_phases.py`

- [ ] **Step 1: Write tests for build_check**

```python
# tests/test_stabilize_phases.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestBuildCheck:
    @pytest.mark.asyncio
    async def test_all_modules_load(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import build_check

        # Create a fake Python package
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("x = 1")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["mypackage/__init__.py", "mypackage/core.py"]}},
        )
        # Mock subprocess to simulate successful imports
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await build_check(ctx)

        assert "build_check" in result
        build = result["build_check"]
        assert len(build.broken) == 0

    @pytest.mark.asyncio
    async def test_broken_module_detected(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import build_check

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["broken/__init__.py"]}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
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

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["pkg/__init__.py"]}},
            emitter=emitter,
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            await build_check(ctx)

        event_types = [e[0] for e in events]
        assert EventType.MECHANICAL_TOOL_STARTED in event_types
        assert EventType.MECHANICAL_TOOL_COMPLETED in event_types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stabilize_phases.py::TestBuildCheck -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'codemonkeys.workflows.phase_library.stabilize'`

- [ ] **Step 3: Implement build_check**

```python
# codemonkeys/workflows/phase_library/stabilize.py
"""Stabilize phases — build check, dependency health, and coverage measurement."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage
from codemonkeys.artifacts.schemas.health import (
    BuildCheckResult,
    DependencyHealthResult,
    OutdatedPackage,
)
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


def _emit_start(ctx: WorkflowContext, tool: str, count: int) -> float:
    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool=tool, files_count=count),
        )
    return time.time()


def _emit_done(ctx: WorkflowContext, tool: str, start: float, count: int) -> None:
    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool=tool, findings_count=count, duration_ms=int((time.time() - start) * 1000)
            ),
        )


async def build_check(ctx: WorkflowContext) -> dict[str, BuildCheckResult]:
    """Try importing all top-level modules to verify the project loads."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    # Extract unique top-level package names from file paths
    modules: set[str] = set()
    for f in files:
        parts = Path(f).parts
        if len(parts) >= 1:
            top = parts[0]
            if top.endswith(".py"):
                top = top[:-3]
            init_path = cwd / top / "__init__.py"
            standalone = cwd / f"{top}.py"
            if init_path.exists() or standalone.exists():
                modules.add(top)

    t = _emit_start(ctx, "build_check", len(modules))

    loadable: list[str] = []
    broken: list[str] = []
    errors: dict[str, str] = {}

    for mod in sorted(modules):
        result = subprocess.run(
            [PYTHON, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode == 0:
            loadable.append(mod)
        else:
            broken.append(mod)
            errors[mod] = (result.stderr or result.stdout).strip()[:500]

    _emit_done(ctx, "build_check", t, len(broken))

    return {"build_check": BuildCheckResult(loadable=loadable, broken=broken, errors=errors)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stabilize_phases.py::TestBuildCheck -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/stabilize.py tests/test_stabilize_phases.py
git commit -m "feat(deep-clean): add build_check stabilize phase"
```

---

### Task 4: Stabilize Phase — dependency_health

**Files:**
- Modify: `codemonkeys/workflows/phase_library/stabilize.py`
- Test: `tests/test_stabilize_phases.py` (append)

- [ ] **Step 1: Write tests for dependency_health**

Add to `tests/test_stabilize_phases.py`:

```python
class TestDependencyHealth:
    @pytest.mark.asyncio
    async def test_detects_missing_lockfile(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import dependency_health

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": []}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": []}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            result = await dependency_health(ctx)

        assert result["dependency_health"].missing_lockfile is False

    @pytest.mark.asyncio
    async def test_detects_outdated_packages(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import dependency_health

        outdated_json = json.dumps([
            {"name": "requests", "version": "2.25.0", "latest_version": "2.31.0"},
        ])

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["app.py"]}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=outdated_json, stderr=""
            )
            result = await dependency_health(ctx)

        assert len(result["dependency_health"].outdated) == 1
        assert result["dependency_health"].outdated[0].name == "requests"
```

Add `import json` at top of file if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stabilize_phases.py::TestDependencyHealth -v`
Expected: FAIL with `ImportError` (function not yet defined)

- [ ] **Step 3: Implement dependency_health**

Add to `codemonkeys/workflows/phase_library/stabilize.py`:

```python
async def dependency_health(ctx: WorkflowContext) -> dict[str, DependencyHealthResult]:
    """Check for unused deps, missing lock file, and outdated packages."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    t = _emit_start(ctx, "dependency_health", len(files))

    # 1. Collect all imports from source files via AST
    import ast

    imported_packages: set[str] = set()
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_packages.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_packages.add(node.module.split(".")[0])

    # 2. Get installed packages
    pip_list = subprocess.run(
        [PYTHON, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    installed_names: set[str] = set()
    if pip_list.returncode == 0 and pip_list.stdout.strip():
        try:
            for pkg in json.loads(pip_list.stdout):
                installed_names.add(pkg["name"].lower().replace("-", "_"))
        except (json.JSONDecodeError, KeyError):
            pass

    # Standard library modules to exclude from "unused" detection
    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

    # Find unused: installed but never imported (rough heuristic)
    imported_normalized = {p.lower().replace("-", "_") for p in imported_packages}
    unused = sorted(
        name for name in installed_names
        if name not in imported_normalized
        and name not in stdlib
        and not name.startswith("_")
    )

    # 3. Check for lock files
    lock_files = ["uv.lock", "poetry.lock"]
    has_lock = any((cwd / lf).exists() for lf in lock_files)
    # Also check for pinned requirements (with == in it)
    req_path = cwd / "requirements.txt"
    if not has_lock and req_path.exists():
        content = req_path.read_text()
        has_lock = "==" in content

    # 4. Check for outdated packages
    outdated_result = subprocess.run(
        [PYTHON, "-m", "pip", "list", "--outdated", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    outdated: list[OutdatedPackage] = []
    if outdated_result.returncode == 0 and outdated_result.stdout.strip():
        try:
            for pkg in json.loads(outdated_result.stdout):
                outdated.append(
                    OutdatedPackage(
                        name=pkg["name"],
                        current=pkg.get("version", ""),
                        latest=pkg.get("latest_version", ""),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            pass

    findings_count = len(unused) + len(outdated) + (1 if not has_lock else 0)
    _emit_done(ctx, "dependency_health", t, findings_count)

    return {
        "dependency_health": DependencyHealthResult(
            unused=unused,
            missing_lockfile=not has_lock,
            outdated=outdated,
        )
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stabilize_phases.py::TestDependencyHealth -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/stabilize.py tests/test_stabilize_phases.py
git commit -m "feat(deep-clean): add dependency_health stabilize phase"
```

---

### Task 5: Stabilize Phase — coverage_measurement

**Files:**
- Modify: `codemonkeys/workflows/phase_library/stabilize.py`
- Test: `tests/test_stabilize_phases.py` (append)

- [ ] **Step 1: Write tests for coverage_measurement**

Add to `tests/test_stabilize_phases.py`:

```python
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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["foo.py", "bar.py"]}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await coverage_measurement(ctx)

        cov = result["coverage"]
        assert cov.overall_percent == 72.5
        assert cov.per_file["bar.py"].percent == 10.0
        # bar.py is below default 40% threshold
        assert "bar.py" in cov.uncovered_files
        assert "foo.py" not in cov.uncovered_files

    @pytest.mark.asyncio
    async def test_handles_pytest_failure(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.stabilize import coverage_measurement

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["foo.py"]}},
        )
        with patch("codemonkeys.workflows.phase_library.stabilize.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=2, stdout="", stderr="no tests ran")
            result = await coverage_measurement(ctx)

        cov = result["coverage"]
        assert cov.overall_percent == 0.0
        assert cov.uncovered_files == ["foo.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stabilize_phases.py::TestCoverageMeasurement -v`
Expected: FAIL

- [ ] **Step 3: Implement coverage_measurement**

Add to `codemonkeys/workflows/phase_library/stabilize.py`:

```python
async def coverage_measurement(ctx: WorkflowContext) -> dict[str, CoverageResult]:
    """Run pytest --cov, parse coverage.json, and identify under-covered files."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]
    threshold: float = getattr(ctx.config, "coverage_threshold", 40.0)

    t = _emit_start(ctx, "coverage", len(files))

    cov_json_path = cwd / "coverage.json"

    subprocess.run(
        [PYTHON, "-m", "pytest", "--cov", "--cov-report=json", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not cov_json_path.exists():
        _emit_done(ctx, "coverage", t, len(files))
        return {
            "coverage": CoverageResult(
                overall_percent=0.0,
                per_file={},
                uncovered_files=list(files),
            )
        }

    try:
        raw = json.loads(cov_json_path.read_text())
    except json.JSONDecodeError:
        _emit_done(ctx, "coverage", t, len(files))
        return {
            "coverage": CoverageResult(
                overall_percent=0.0,
                per_file={},
                uncovered_files=list(files),
            )
        }

    overall = raw.get("totals", {}).get("percent_covered", 0.0)
    per_file: dict[str, FileCoverage] = {}
    uncovered: list[str] = []

    raw_files = raw.get("files", {})
    for f in files:
        file_data = raw_files.get(f)
        if not file_data:
            uncovered.append(f)
            continue
        summary = file_data.get("summary", {})
        fc = FileCoverage(
            lines_covered=summary.get("covered_lines", 0),
            lines_missed=summary.get("missing_lines", 0),
            percent=summary.get("percent_covered", 0.0),
        )
        per_file[f] = fc
        if fc.percent < threshold:
            uncovered.append(f)

    _emit_done(ctx, "coverage", t, len(uncovered))

    return {
        "coverage": CoverageResult(
            overall_percent=overall,
            per_file=per_file,
            uncovered_files=uncovered,
        )
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stabilize_phases.py::TestCoverageMeasurement -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/stabilize.py tests/test_stabilize_phases.py
git commit -m "feat(deep-clean): add coverage_measurement stabilize phase"
```

---

### Task 6: Structural Analysis Phase

**Files:**
- Create: `codemonkeys/workflows/phase_library/structural.py`
- Test: `tests/test_structural_phase.py`

- [ ] **Step 1: Write tests for import graph and cycle detection**

```python
# tests/test_structural_phase.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={
                "discover": {"files": ["a.py", "b.py", "c.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch("codemonkeys.workflows.phase_library.structural.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await structural_analysis(ctx)

        report = result["structural_report"]
        assert "b" in report.import_graph.get("a.py", []) or "b.py" in report.import_graph.get("a.py", [])

    @pytest.mark.asyncio
    async def test_detects_circular_deps(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.structural import structural_analysis

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("import a\n")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
            phase_results={
                "discover": {"files": ["a.py", "b.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch("codemonkeys.workflows.phase_library.structural.subprocess") as mock_sub:
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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={
                "discover": {"files": ["mod.py"]},
                "coverage": {"coverage": MagicMock(per_file={}, uncovered_files=[])},
            },
        )
        with patch("codemonkeys.workflows.phase_library.structural.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await structural_analysis(ctx)

        metrics = result["structural_report"].file_metrics["mod.py"]
        assert metrics.function_count == 2
        assert metrics.class_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_structural_phase.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement structural_analysis**

```python
# codemonkeys/workflows/phase_library/structural.py
"""Structural analysis phase — import graph, cycle detection, complexity metrics."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import time
from pathlib import Path

from codemonkeys.artifacts.schemas.structural import (
    FileMetrics,
    HotFile,
    LayerViolation,
    NamingIssue,
    StructuralReport,
)
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


def _build_import_graph(files: list[str], cwd: Path) -> dict[str, list[str]]:
    """Parse AST imports for each file, resolving to file paths within the project."""
    file_set = set(files)
    # Map module name -> file path (for resolution)
    module_to_file: dict[str, str] = {}
    for f in files:
        parts = Path(f).with_suffix("").parts
        module_to_file[".".join(parts)] = f
        # Also register the top-level stem for standalone files
        if len(parts) == 1:
            module_to_file[parts[0]] = f

    graph: dict[str, list[str]] = {}
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            graph[f] = []
            continue

        imports: list[str] = []
        for node in ast.walk(tree):
            mod_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module

            if mod_name:
                # Try to resolve to a project file
                top = mod_name.split(".")[0]
                resolved = module_to_file.get(mod_name) or module_to_file.get(top)
                if resolved and resolved != f:
                    imports.append(resolved)

        graph[f] = sorted(set(imports))

    return graph


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Find strongly connected components using Tarjan's algorithm."""
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for neighbor in graph.get(node, []):
            if neighbor not in index:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif on_stack.get(neighbor, False):
                lowlink[node] = min(lowlink[node], index[neighbor])

        if lowlink[node] == index[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(sorted(scc))

    for node in graph:
        if node not in index:
            strongconnect(node)

    return sccs


def _compute_file_metrics(files: list[str], cwd: Path) -> dict[str, FileMetrics]:
    """Compute line count, function/class counts, and max function length per file."""
    metrics: dict[str, FileMetrics] = {}
    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue

        lines = len(source.splitlines())
        func_count = 0
        class_count = 0
        max_func_len = 0

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                func_count += 1
                func_len = (node.end_lineno or node.lineno) - node.lineno + 1
                max_func_len = max(max_func_len, func_len)
            elif isinstance(node, ast.ClassDef):
                class_count += 1

        metrics[f] = FileMetrics(
            lines=lines,
            function_count=func_count,
            class_count=class_count,
            max_function_length=max_func_len,
        )

    return metrics


def _detect_naming_issues(files: list[str], cwd: Path) -> list[NamingIssue]:
    """Find top-level identifiers that don't follow snake_case convention."""
    issues: list[NamingIssue] = []
    camel_re = re.compile(r"[a-z][A-Z]")

    for f in files:
        full_path = cwd / f
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=f)
        except (SyntaxError, OSError):
            continue

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if camel_re.search(node.name) and not node.name.startswith("_"):
                    snake = re.sub(r"([A-Z])", r"_\1", node.name).lower().lstrip("_")
                    issues.append(
                        NamingIssue(
                            file=f,
                            name=node.name,
                            expected_convention="snake_case",
                            suggestion=snake,
                        )
                    )

    return issues


def _compute_hot_files(
    files: list[str], import_graph: dict[str, list[str]], cwd: Path
) -> list[HotFile]:
    """Score files by git churn * import fanout."""
    # Count importers per file
    importer_count: dict[str, int] = {f: 0 for f in files}
    for _src, targets in import_graph.items():
        for t in targets:
            if t in importer_count:
                importer_count[t] += 1

    # Get git churn
    churn: dict[str, int] = {}
    result = subprocess.run(
        ["git", "log", "--format=%H"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        commits = result.stdout.strip().splitlines()[:200]
        for commit in commits:
            diff_result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            if diff_result.returncode == 0:
                for f in diff_result.stdout.strip().splitlines():
                    if f in importer_count:
                        churn[f] = churn.get(f, 0) + 1

    hot: list[HotFile] = []
    for f in files:
        c = churn.get(f, 0)
        i = importer_count.get(f, 0)
        if c > 0 or i > 0:
            hot.append(HotFile(file=f, churn=c, importers=i, risk_score=c * max(i, 1)))

    return sorted(hot, key=lambda h: h.risk_score, reverse=True)


def _build_test_source_map(coverage_result: object) -> dict[str, list[str]]:
    """Build test->source mapping from coverage data.

    This is a simplified version that maps test files to source files
    based on naming convention (test_foo.py -> foo.py). The actual
    coverage.json from pytest-cov contains execution data for source
    files, not per-test mappings, so we combine naming + coverage data.
    """
    # coverage_result is a CoverageResult — use per_file keys
    per_file = getattr(coverage_result, "per_file", {})
    test_map: dict[str, list[str]] = {}

    test_files = [f for f in per_file if "test" in Path(f).name.lower()]
    source_files = [f for f in per_file if "test" not in Path(f).name.lower()]

    for tf in test_files:
        stem = Path(tf).stem
        if stem.startswith("test_"):
            src_stem = stem[5:]  # remove "test_" prefix
        else:
            continue
        matched = [sf for sf in source_files if Path(sf).stem == src_stem]
        if matched:
            test_map[tf] = matched

    return test_map


async def structural_analysis(ctx: WorkflowContext) -> dict[str, StructuralReport]:
    """Build the StructuralReport: import graph, cycles, metrics, naming, hot files."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]

    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool="structural_analysis", files_count=len(files)),
        )
    start = time.time()

    import_graph = _build_import_graph(files, cwd)
    circular_deps = _find_cycles(import_graph)
    file_metrics = _compute_file_metrics(files, cwd)
    naming_issues = _detect_naming_issues(files, cwd)
    hot_files = _compute_hot_files(files, import_graph, cwd)

    # Layer violations require config rules
    layer_rules: dict[str, list[str]] = getattr(ctx.config, "layer_rules", None) or {}
    layer_violations: list[LayerViolation] = []
    for src_file, targets in import_graph.items():
        for rule_module, forbidden in layer_rules.items():
            if rule_module in src_file:
                for target in targets:
                    for forbidden_mod in forbidden:
                        if forbidden_mod in target:
                            layer_violations.append(
                                LayerViolation(
                                    source_file=src_file,
                                    target_file=target,
                                    rule=f"{rule_module} cannot import from {forbidden_mod}",
                                )
                            )

    # Build test-source map from coverage results if available
    coverage_result = ctx.phase_results.get("coverage", {}).get("coverage")
    test_source_map = _build_test_source_map(coverage_result) if coverage_result else {}

    findings_count = (
        len(circular_deps) + len(layer_violations) + len(naming_issues)
    )

    if ctx.emitter:
        ctx.emitter.emit(
            EventType.MECHANICAL_TOOL_COMPLETED,
            MechanicalToolCompletedPayload(
                tool="structural_analysis",
                findings_count=findings_count,
                duration_ms=int((time.time() - start) * 1000),
            ),
        )

    return {
        "structural_report": StructuralReport(
            import_graph=import_graph,
            circular_deps=circular_deps,
            file_metrics=file_metrics,
            layer_violations=layer_violations,
            naming_issues=naming_issues,
            test_source_map=test_source_map,
            hot_files=hot_files,
        )
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_structural_phase.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/structural.py tests/test_structural_phase.py
git commit -m "feat(deep-clean): add structural_analysis phase with Tarjan's SCC"
```

---

### Task 7: Agent — python_characterization_tester

**Files:**
- Create: `codemonkeys/core/agents/python_characterization_tester.py`
- Test: `tests/test_characterization_tester.py`

- [ ] **Step 1: Write tests for the agent factory**

```python
# tests/test_characterization_tester.py
from __future__ import annotations


class TestMakeCharacterizationTester:
    def test_creates_agent_definition(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["core/runner.py", "core/analysis.py"],
            import_context="core/runner.py imports: analysis, sandbox",
            uncovered_lines={"core/runner.py": [10, 20, 30], "core/analysis.py": [5, 15]},
        )
        assert agent.model == "sonnet"
        assert "Read" in agent.tools
        assert "Write" in agent.tools
        assert any("pytest" in t for t in agent.tools)
        assert "runner.py" in agent.prompt
        assert "analysis.py" in agent.prompt
        assert "MUST pass" in agent.prompt or "must pass" in agent.prompt.lower()

    def test_prompt_includes_uncovered_lines(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["foo.py"],
            import_context="foo.py imports: bar",
            uncovered_lines={"foo.py": [42, 99]},
        )
        assert "42" in agent.prompt
        assert "99" in agent.prompt

    def test_permission_mode(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["x.py"],
            import_context="",
            uncovered_lines={},
        )
        assert agent.permissionMode == "acceptEdits"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_characterization_tester.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the agent factory**

```python
# codemonkeys/core/agents/python_characterization_tester.py
"""Characterization test writer — locks current behavior for uncovered files."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import PYTHON_CMD, PYTHON_GUIDELINES


def make_python_characterization_tester(
    files: list[str],
    import_context: str,
    uncovered_lines: dict[str, list[int]],
) -> AgentDefinition:
    file_list = "\n".join(f"- `{f}`" for f in files)

    uncovered_section = ""
    for f, lines in uncovered_lines.items():
        if lines:
            line_str = ", ".join(str(ln) for ln in lines[:50])
            uncovered_section += f"\n### `{f}` — uncovered lines: {line_str}\n"

    return AgentDefinition(
        description=f"Write characterization tests for {len(files)} file(s)",
        prompt=f"""\
You write characterization tests that lock the current behavior of existing code.
Your goal is to maximize line coverage for the files listed below.

## Files to Test

{file_list}

## Import Context

{import_context}

## Uncovered Lines
{uncovered_section}

## Method

1. Read each source file to understand what it does.
2. Write test files following the naming convention `tests/test_<stem>.py`.
3. Write tests that exercise the uncovered lines listed above.
4. Focus on testing observable behavior: return values, side effects, exceptions.
5. Run `{PYTHON_CMD} -m pytest <test_file> -v` to verify every test passes.
6. If a test fails, fix the TEST — never modify the source code.

## Rules

- Tests MUST pass. They characterize what the code does now, not what it should do.
- Do not modify source files under any circumstances.
- Do not add type stubs, fixtures, or conftest changes unless necessary for import.
- Prefer simple, direct tests over elaborate fixtures.
- Use `unittest.mock.patch` sparingly — only when the code has side effects
  (file I/O, network, subprocess) that cannot be avoided.
- Name tests descriptively: `test_<function>_<scenario>`.
- Maximum 2 test-fix cycles per file. If tests still fail, move on.

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Write",
            "Grep",
            f"Bash({PYTHON_CMD} -m pytest*)",
        ],
        permissionMode="acceptEdits",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_characterization_tester.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/agents/python_characterization_tester.py tests/test_characterization_tester.py
git commit -m "feat(deep-clean): add python_characterization_tester agent"
```

---

### Task 8: Agent — python_structural_refactorer

**Files:**
- Create: `codemonkeys/core/agents/python_structural_refactorer.py`
- Test: `tests/test_structural_refactorer.py`

- [ ] **Step 1: Write tests for the agent factory**

```python
# tests/test_structural_refactorer.py
from __future__ import annotations


class TestMakeStructuralRefactorer:
    def test_creates_agent_definition(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            make_python_structural_refactorer,
        )

        agent = make_python_structural_refactorer(
            files=["a.py", "b.py"],
            problem_description="Circular dependency: a.py -> b.py -> a.py",
            refactor_type="circular_deps",
            test_files=["tests/test_a.py"],
        )
        assert agent.model == "sonnet"
        assert "Edit" in agent.tools
        assert "Write" in agent.tools
        assert any("pytest" in t for t in agent.tools)
        assert any("ruff" in t for t in agent.tools)
        assert "a.py" in agent.prompt
        assert "Circular dependency" in agent.prompt

    def test_includes_scoped_test_command(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            make_python_structural_refactorer,
        )

        agent = make_python_structural_refactorer(
            files=["core/runner.py"],
            problem_description="God module: 500 lines, 15 functions",
            refactor_type="god_modules",
            test_files=["tests/test_runner.py"],
        )
        assert "tests/test_runner.py" in agent.prompt

    def test_all_refactor_types(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            REFACTOR_INSTRUCTIONS,
            make_python_structural_refactorer,
        )

        for refactor_type in REFACTOR_INSTRUCTIONS:
            agent = make_python_structural_refactorer(
                files=["x.py"],
                problem_description="test",
                refactor_type=refactor_type,
                test_files=[],
            )
            assert agent.model == "sonnet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_structural_refactorer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the agent factory**

```python
# codemonkeys/core/agents/python_structural_refactorer.py
"""Structural refactorer — executes scoped structural changes guided by StructuralReport."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES

REFACTOR_INSTRUCTIONS: dict[str, str] = {
    "circular_deps": """\
Break the circular dependency described below. Common strategies:
- Extract shared types/interfaces into a third module both can import.
- Invert the dependency direction using dependency injection.
- Merge the modules if they are conceptually one unit.
- Use late imports (inside functions) only as a last resort.""",
    "layering": """\
Fix the layer violation described below. The import crosses a boundary
that should be respected. Move the shared code to the appropriate layer,
or restructure so the lower layer doesn't depend on the higher one.""",
    "god_modules": """\
Split the oversized module into focused, single-responsibility modules.
- Identify cohesive groups of functions/classes that work together.
- Extract each group into its own module.
- Update imports across the codebase to point to the new locations.
- The original module can re-export for backwards compatibility if needed.""",
    "extract_shared": """\
Extract duplicated code into a shared module.
- Identify the common pattern across the duplicate sites.
- Create a single implementation in an appropriate shared location.
- Replace all duplicate sites with calls to the shared code.
- Ensure the shared interface is clean and well-named.""",
    "dead_code": """\
Remove the dead code identified below. Verify it is truly unreachable:
- Check for dynamic references (getattr, importlib, string-based dispatch).
- Check for use in tests, scripts, or CLI entry points.
- If truly dead, delete it cleanly with no stubs or comments.""",
    "naming": """\
Rename the inconsistent identifiers below to match the codebase convention.
- Update ALL references across the codebase (imports, calls, strings).
- Use your editor tools to find all occurrences before renaming.
- Verify no references are missed after renaming.""",
}


def make_python_structural_refactorer(
    files: list[str],
    problem_description: str,
    refactor_type: str,
    test_files: list[str],
) -> AgentDefinition:
    file_list = "\n".join(f"- `{f}`" for f in files)
    instructions = REFACTOR_INSTRUCTIONS.get(refactor_type, "Follow the problem description below.")

    test_cmd = f"{PYTHON_CMD} -m pytest -x -q --tb=short --no-header"
    if test_files:
        test_cmd += " " + " ".join(test_files)

    return AgentDefinition(
        description=f"Refactor ({refactor_type}): {', '.join(files)}",
        prompt=f"""\
You are a structural refactoring agent. You make targeted structural changes
to improve codebase organization. You only touch the files listed below.

## Refactor Type: {refactor_type}

{instructions}

## Problem

{problem_description}

## Files You May Modify

{file_list}

## Scoped Test Command

After making changes, run:
```
{test_cmd}
```

## Method

1. Read all listed files to understand the current structure.
2. Plan the minimal structural change that solves the problem.
3. Make the changes.
4. Run `{PYTHON_CMD} -m ruff check --fix .` and `{PYTHON_CMD} -m ruff format .`
5. Run the scoped test command above.
6. If tests fail, fix the issue. Maximum 2 fix cycles.

## Rules

- Only touch files listed above. If you need to create a new file to
  extract code into, that's allowed.
- Make the minimal change. Don't improve code style, add features, or
  refactor beyond the stated problem.
- Preserve all public interfaces unless the problem requires changing them.
- Do not commit, push, or modify git state.

{ENGINEERING_MINDSET}

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Grep",
            "Edit",
            "Write",
            f"Bash({PYTHON_CMD} -m pytest*)",
            f"Bash({PYTHON_CMD} -m ruff*)",
        ],
        permissionMode="acceptEdits",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_structural_refactorer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/agents/python_structural_refactorer.py tests/test_structural_refactorer.py
git commit -m "feat(deep-clean): add python_structural_refactorer agent"
```

---

### Task 9: Characterization Test Phase Function

**Files:**
- Modify: `codemonkeys/workflows/phase_library/structural.py`
- Test: `tests/test_structural_phase.py` (append)

- [ ] **Step 1: Write test for characterization_tests phase**

Add to `tests/test_structural_phase.py`:

```python
from unittest.mock import AsyncMock


class TestCharacterizationTests:
    @pytest.mark.asyncio
    async def test_dispatches_agents_for_uncovered_files(self, tmp_path: Path) -> None:
        from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage
        from codemonkeys.artifacts.schemas.refactor import CharTestResult
        from codemonkeys.workflows.phase_library.structural import characterization_tests

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
            config=ReviewConfig(mode="deep_clean"),
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
        # Should have dispatched for foo.py (uncovered) but not bar.py (80% covered)
        assert instance.run_agent.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_when_no_uncovered_files(self, tmp_path: Path) -> None:
        from codemonkeys.artifacts.schemas.coverage import CoverageResult
        from codemonkeys.workflows.phase_library.structural import characterization_tests

        coverage = CoverageResult(
            overall_percent=95.0,
            per_file={},
            uncovered_files=[],
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="deep_clean"),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_structural_phase.py::TestCharacterizationTests -v`
Expected: FAIL

- [ ] **Step 3: Implement characterization_tests phase**

Add to `codemonkeys/workflows/phase_library/structural.py`:

```python
import asyncio
from typing import Any

from codemonkeys.artifacts.schemas.refactor import CharTestResult
from codemonkeys.core.agents.python_characterization_tester import (
    make_python_characterization_tester,
)
from codemonkeys.core.runner import AgentRunner


async def _run_char_test_batch(
    batch_files: list[str],
    import_graph: dict[str, list[str]],
    uncovered_lines: dict[str, list[int]],
    ctx: WorkflowContext,
    semaphore: asyncio.Semaphore,
) -> CharTestResult:
    """Dispatch a characterization tester agent for a batch of files."""
    async with semaphore:
        # Build import context string
        import_strs = []
        for f in batch_files:
            deps = import_graph.get(f, [])
            if deps:
                import_strs.append(f"{f} imports: {', '.join(deps)}")
        import_context = "\n".join(import_strs)

        batch_uncovered = {f: uncovered_lines.get(f, []) for f in batch_files}

        agent = make_python_characterization_tester(
            files=batch_files,
            import_context=import_context,
            uncovered_lines=batch_uncovered,
        )

        runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
        output_format: dict[str, Any] = {
            "type": "json_schema",
            "schema": CharTestResult.model_json_schema(),
        }
        result = await runner.run_agent(
            agent,
            f"Write characterization tests for: {', '.join(batch_files)}",
            output_format=output_format,
            log_name=f"char_test__{batch_files[0]}",
        )

        if result.structured:
            return CharTestResult.model_validate(result.structured)
        return CharTestResult(
            tests_written=[], files_covered=batch_files, coverage_after=None
        )


async def characterization_tests(ctx: WorkflowContext) -> dict[str, list[CharTestResult]]:
    """Dispatch characterization test writers for uncovered files."""
    coverage_result = ctx.phase_results.get("coverage", {}).get("coverage")
    if not coverage_result:
        return {"char_test_results": []}

    uncovered_files: list[str] = coverage_result.uncovered_files
    if not uncovered_files:
        return {"char_test_results": []}

    structural_report = ctx.phase_results.get("structural_analysis", {}).get(
        "structural_report"
    )
    import_graph: dict[str, list[str]] = (
        structural_report.import_graph if structural_report else {}
    )

    # Build uncovered lines map from coverage per_file data
    uncovered_lines: dict[str, list[int]] = {}
    for f in uncovered_files:
        file_cov = coverage_result.per_file.get(f)
        if file_cov:
            uncovered_lines[f] = []  # coverage.json doesn't give per-line detail by default

    # Batch: up to 3 files per agent
    batches: list[list[str]] = []
    current_batch: list[str] = []
    for f in uncovered_files:
        current_batch.append(f)
        if len(current_batch) == 3:
            batches.append(current_batch)
            current_batch = []
    if current_batch:
        batches.append(current_batch)

    config = ctx.config
    max_concurrent = getattr(config, "max_concurrent", 5)
    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = [
        _run_char_test_batch(batch, import_graph, uncovered_lines, ctx, semaphore)
        for batch in batches
    ]
    results = await asyncio.gather(*tasks)

    return {"char_test_results": list(results)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_structural_phase.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/structural.py tests/test_structural_phase.py
git commit -m "feat(deep-clean): add characterization_tests phase with batched dispatch"
```

---

### Task 10: Refactor Phase — refactor_step, update_readme, final_verify

**Files:**
- Create: `codemonkeys/workflows/phase_library/refactor.py`
- Test: `tests/test_refactor_phase.py`

- [ ] **Step 1: Write tests for refactor_step**

```python
# tests/test_refactor_phase.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.structural import StructuralReport, FileMetrics, HotFile
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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={
                "structural_analysis": {
                    "structural_report": _make_structural_report()
                },
            },
            user_input="approve",
        )
        # refactor_circular_deps with no cycles -> skip
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
            config=ReviewConfig(mode="deep_clean"),
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
            config=ReviewConfig(mode="deep_clean"),
            phase_results={"discover": {"files": ["foo.py"]}},
        )

        with patch("codemonkeys.workflows.phase_library.refactor.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await final_verify(ctx)

        v = result["verification"]
        assert v.tests_passed is True
        assert v.lint_passed is True
        assert v.typecheck_passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refactor_phase.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement refactor_step, update_readme, final_verify**

```python
# codemonkeys/workflows/phase_library/refactor.py
"""Refactor phases — gated structural refactoring, README update, final verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.refactor import StructuralRefactorResult
from codemonkeys.artifacts.schemas.results import VerificationResult
from codemonkeys.artifacts.schemas.structural import StructuralReport
from codemonkeys.core.agents.python_structural_refactorer import (
    make_python_structural_refactorer,
)
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable

_STEP_TO_DATA: dict[str, str] = {
    "refactor_circular_deps": "circular_deps",
    "refactor_layering": "layer_violations",
    "refactor_god_modules": "file_metrics",
    "refactor_extract_shared": "file_metrics",
    "refactor_dead_code": "file_metrics",
    "refactor_naming": "naming_issues",
}

_STEP_TO_REFACTOR_TYPE: dict[str, str] = {
    "refactor_circular_deps": "circular_deps",
    "refactor_layering": "layering",
    "refactor_god_modules": "god_modules",
    "refactor_extract_shared": "extract_shared",
    "refactor_dead_code": "dead_code",
    "refactor_naming": "naming",
}


def _extract_issues_for_step(
    step_name: str, report: StructuralReport
) -> tuple[list[str], str]:
    """Extract affected files and problem description from the structural report."""
    refactor_type = _STEP_TO_REFACTOR_TYPE.get(step_name, "")

    if refactor_type == "circular_deps":
        if not report.circular_deps:
            return [], ""
        files: set[str] = set()
        descs: list[str] = []
        for cycle in report.circular_deps:
            files.update(cycle)
            descs.append(" -> ".join(cycle) + f" -> {cycle[0]}")
        return sorted(files), "Circular dependencies:\n" + "\n".join(descs)

    if refactor_type == "layering":
        if not report.layer_violations:
            return [], ""
        files = set()
        descs = []
        for v in report.layer_violations:
            files.add(v.source_file)
            files.add(v.target_file)
            descs.append(f"{v.source_file} imports {v.target_file} ({v.rule})")
        return sorted(files), "Layer violations:\n" + "\n".join(descs)

    if refactor_type == "god_modules":
        GOD_MODULE_THRESHOLD = 300
        big_files = [
            (f, m)
            for f, m in report.file_metrics.items()
            if m.lines > GOD_MODULE_THRESHOLD
        ]
        if not big_files:
            return [], ""
        files_list = [f for f, _ in big_files]
        descs = [
            f"{f} ({m.lines} lines, {m.function_count} functions, {m.class_count} classes)"
            for f, m in big_files
        ]
        return files_list, "Oversized modules:\n" + "\n".join(descs)

    if refactor_type == "extract_shared":
        # Reuse god module analysis for now — files with many functions may contain duplicated logic
        threshold = 8
        candidates = [
            (f, m)
            for f, m in report.file_metrics.items()
            if m.function_count > threshold
        ]
        if not candidates:
            return [], ""
        files_list = [f for f, _ in candidates]
        descs = [
            f"{f} ({m.function_count} functions — check for extractable shared logic)"
            for f, m in candidates
        ]
        return files_list, "Potential duplication:\n" + "\n".join(descs)

    if refactor_type == "dead_code":
        # Dead code is detected in mechanical audit, but we can also flag
        # files with 0 importers and low churn from hot_files
        dead_candidates = [
            h.file for h in report.hot_files if h.importers == 0 and h.churn == 0
        ]
        if not dead_candidates:
            return [], ""
        return dead_candidates, "Potentially dead modules (0 importers, 0 churn):\n" + "\n".join(
            f"- {f}" for f in dead_candidates
        )

    if refactor_type == "naming":
        if not report.naming_issues:
            return [], ""
        files = sorted({n.file for n in report.naming_issues})
        descs = [
            f"{n.file}: `{n.name}` -> `{n.suggestion}` ({n.expected_convention})"
            for n in report.naming_issues
        ]
        return files, "Naming inconsistencies:\n" + "\n".join(descs)

    return [], ""


async def refactor_step(
    ctx: WorkflowContext, *, step_name: str | None = None
) -> dict[str, Any]:
    """Execute a single refactoring step. Called with step_name to identify which step."""
    # The workflow engine stores phase results under the phase name.
    # The step_name parameter lets the same function handle all 6 steps.
    # When called from the engine, we need to determine which step we are.
    # The phase name is passed via step_name when called directly,
    # or we check which phase hasn't been stored yet.
    report: StructuralReport = ctx.phase_results["structural_analysis"]["structural_report"]

    if not step_name:
        # Determine step from context — find which refactor phase hasn't run yet
        for name in _STEP_TO_REFACTOR_TYPE:
            if name not in ctx.phase_results:
                step_name = name
                break
        if not step_name:
            return {"skipped": True, "refactor_result": None}

    affected_files, problem_description = _extract_issues_for_step(step_name, report)

    if not affected_files:
        return {"skipped": True, "refactor_result": None}

    # Check user input — if "skip" was sent, skip this step
    if ctx.user_input and isinstance(ctx.user_input, str) and ctx.user_input.lower() == "skip":
        return {"skipped": True, "refactor_result": None}

    # Find scoped tests from test_source_map
    test_files: list[str] = []
    for test_file, source_files in report.test_source_map.items():
        if any(sf in affected_files for sf in source_files):
            test_files.append(test_file)

    refactor_type = _STEP_TO_REFACTOR_TYPE[step_name]
    agent = make_python_structural_refactorer(
        files=affected_files,
        problem_description=problem_description,
        refactor_type=refactor_type,
        test_files=test_files,
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    output_format: dict[str, Any] = {
        "type": "json_schema",
        "schema": StructuralRefactorResult.model_json_schema(),
    }
    result = await runner.run_agent(
        agent,
        f"Refactor ({refactor_type}): {problem_description[:200]}",
        output_format=output_format,
        log_name=f"refactor__{step_name}",
    )

    if result.structured:
        refactor_result = StructuralRefactorResult.model_validate(result.structured)
    else:
        refactor_result = StructuralRefactorResult(
            files_changed=[], description="Could not parse agent output", tests_passed=False
        )

    return {"skipped": False, "refactor_result": refactor_result}


async def update_readme(ctx: WorkflowContext) -> dict[str, Any]:
    """Update README.md using the refreshed StructuralReport."""
    import json

    report: StructuralReport = ctx.phase_results.get("rescan_structure", ctx.phase_results.get("structural_analysis", {})).get(
        "structural_report"
    )
    if not report:
        return {"readme_updated": False}

    cwd = Path(ctx.cwd)
    readme_path = cwd / "README.md"
    if not readme_path.exists():
        return {"readme_updated": False}

    # Use the fixer pattern — give an agent the README + structural summary
    from codemonkeys.core.prompts import PYTHON_CMD

    report_summary = json.dumps(
        {
            "files": sorted(report.import_graph.keys()),
            "modules": sorted({f.split("/")[0] for f in report.import_graph}),
            "file_count": len(report.import_graph),
        },
        indent=2,
    )

    from claude_agent_sdk import AgentDefinition

    agent = AgentDefinition(
        description="Update README.md to reflect refactored structure",
        prompt=f"""\
You update a project's README.md to match the current codebase structure.
You are given a structural summary showing the current files and modules.

## Structural Summary

```json
{report_summary}
```

## Method

1. Read README.md.
2. Update any file paths, module references, or structure descriptions
   that no longer match the structural summary above.
3. Do NOT change the README's tone, purpose, or non-structural content.
4. If the README is already accurate, make no changes.

## Rules

- Only update structural references. Don't rewrite prose.
- Don't add new sections. Only fix inaccuracies.
- Run `{PYTHON_CMD} -m ruff format README.md` if you changed it (skip if it's not a .py file).""",
        model="sonnet",
        tools=["Read", "Edit"],
        permissionMode="acceptEdits",
    )

    runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
    await runner.run_agent(agent, "Update README.md", log_name="update_readme")

    return {"readme_updated": True}


async def final_verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    """Run the full mechanical suite: pytest, ruff, pyright, import check."""
    cwd = Path(ctx.cwd)

    tests = subprocess.run(
        [PYTHON, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    lint = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    typecheck = subprocess.run(
        [PYTHON, "-m", "pyright", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    errors: list[str] = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")
    if typecheck.returncode != 0:
        errors.append(f"pyright: {typecheck.stdout[:500]}")

    # Import check
    files: list[str] = ctx.phase_results.get("discover", {}).get("files", [])
    modules: set[str] = set()
    for f in files:
        parts = Path(f).parts
        if parts:
            modules.add(parts[0].replace(".py", ""))

    for mod in modules:
        result = subprocess.run(
            [PYTHON, "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            errors.append(f"import {mod}: {result.stderr[:200]}")

    return {
        "verification": VerificationResult(
            tests_passed=tests.returncode == 0,
            lint_passed=lint.returncode == 0,
            typecheck_passed=typecheck.returncode == 0,
            errors=errors,
        )
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_refactor_phase.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/refactor.py tests/test_refactor_phase.py
git commit -m "feat(deep-clean): add refactor_step, update_readme, and final_verify phases"
```

---

### Task 11: Phase Library Exports & Workflow Composition

**Files:**
- Modify: `codemonkeys/workflows/phase_library/__init__.py`
- Modify: `codemonkeys/workflows/compositions.py`
- Test: `tests/test_compositions.py` (append)

- [ ] **Step 1: Write test for the new workflow composition**

Add to `tests/test_compositions.py`:

```python
class TestDeepCleanWorkflow:
    def test_deep_clean_workflow_has_expected_phases(self) -> None:
        from codemonkeys.workflows.compositions import make_deep_clean_workflow

        wf = make_deep_clean_workflow()
        names = [p.name for p in wf.phases]

        # Stabilize phases
        assert "build_check" in names
        assert "dependency_health" in names
        assert "coverage" in names
        assert "structural_analysis" in names
        assert "characterization_tests" in names

        # Refactor phases (all GATE)
        refactor_names = [n for n in names if n.startswith("refactor_")]
        assert len(refactor_names) == 6

        # Finalize phases
        assert "rescan_structure" in names
        assert "update_readme" in names
        assert "final_verify" in names
        assert "report" in names

    def test_refactor_phases_are_gates(self) -> None:
        from codemonkeys.workflows.compositions import make_deep_clean_workflow
        from codemonkeys.workflows.phases import PhaseType

        wf = make_deep_clean_workflow()
        for phase in wf.phases:
            if phase.name.startswith("refactor_"):
                assert phase.phase_type == PhaseType.GATE, f"{phase.name} should be GATE"

    def test_deep_clean_config(self) -> None:
        from codemonkeys.workflows.compositions import ReviewConfig

        config = ReviewConfig(mode="deep_clean")
        assert "dead_code" in config.audit_tools
        assert "pip_audit" in config.audit_tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_compositions.py::TestDeepCleanWorkflow -v`
Expected: FAIL

- [ ] **Step 3: Update phase_library __init__.py exports**

```python
# codemonkeys/workflows/phase_library/__init__.py
"""Reusable phase functions for review workflows."""

from __future__ import annotations

from codemonkeys.workflows.phase_library.action import fix, report, triage, verify
from codemonkeys.workflows.phase_library.discovery import (
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
)
from codemonkeys.workflows.phase_library.mechanical import mechanical_audit
from codemonkeys.workflows.phase_library.refactor import (
    final_verify,
    refactor_step,
    update_readme,
)
from codemonkeys.workflows.phase_library.review import (
    architecture_review,
    doc_review,
    file_review,
    spec_compliance_review,
)
from codemonkeys.workflows.phase_library.stabilize import (
    build_check,
    coverage_measurement,
    dependency_health,
)
from codemonkeys.workflows.phase_library.structural import (
    characterization_tests,
    structural_analysis,
)

__all__ = [
    "architecture_review",
    "build_check",
    "characterization_tests",
    "coverage_measurement",
    "dependency_health",
    "discover_all_files",
    "discover_diff",
    "discover_files",
    "discover_from_spec",
    "doc_review",
    "file_review",
    "final_verify",
    "fix",
    "mechanical_audit",
    "refactor_step",
    "report",
    "spec_compliance_review",
    "structural_analysis",
    "triage",
    "update_readme",
    "verify",
]
```

- [ ] **Step 4: Update compositions.py**

Add to imports in `codemonkeys/workflows/compositions.py`:

```python
from codemonkeys.workflows.phase_library import (
    # ... existing imports ...
    build_check,
    characterization_tests,
    coverage_measurement,
    dependency_health,
    final_verify,
    refactor_step,
    structural_analysis,
    update_readme,
)
```

Update `ReviewConfig.mode` type:

```python
mode: Literal["full_repo", "diff", "files", "post_feature", "deep_clean"]
```

Add new fields to `ReviewConfig`:

```python
coverage_threshold: float = 40.0
layer_rules: dict[str, list[str]] | None = None
```

Add to `_MODE_TOOLS`:

```python
_MODE_TOOLS["deep_clean"] = ALL_TOOLS
```

Add the workflow builder:

```python
def make_deep_clean_workflow() -> Workflow:
    """Deep clean — stabilize, write characterization tests, incrementally refactor."""

    def _make_refactor_phase(name: str) -> Phase:
        async def _execute(ctx: WorkflowContext) -> dict:
            return await refactor_step(ctx, step_name=name)
        return Phase(name=name, phase_type=PhaseType.GATE, execute=_execute)

    return Workflow(
        name="deep_clean",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_all_files),
            Phase(name="build_check", phase_type=PhaseType.AUTOMATED, execute=build_check),
            Phase(name="dependency_health", phase_type=PhaseType.AUTOMATED, execute=dependency_health),
            Phase(name="coverage", phase_type=PhaseType.AUTOMATED, execute=coverage_measurement),
            Phase(name="structural_analysis", phase_type=PhaseType.AUTOMATED, execute=structural_analysis),
            Phase(name="characterization_tests", phase_type=PhaseType.AUTOMATED, execute=characterization_tests),
            _make_refactor_phase("refactor_circular_deps"),
            _make_refactor_phase("refactor_layering"),
            _make_refactor_phase("refactor_god_modules"),
            _make_refactor_phase("refactor_extract_shared"),
            _make_refactor_phase("refactor_dead_code"),
            _make_refactor_phase("refactor_naming"),
            Phase(name="rescan_structure", phase_type=PhaseType.AUTOMATED, execute=structural_analysis),
            Phase(name="update_readme", phase_type=PhaseType.AUTOMATED, execute=update_readme),
            Phase(name="final_verify", phase_type=PhaseType.AUTOMATED, execute=final_verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )
```

Note: the `_make_refactor_phase` closure binds the step name so the generic `refactor_step` function knows which step to execute.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_compositions.py::TestDeepCleanWorkflow -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All existing tests still pass, new tests pass

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phase_library/__init__.py codemonkeys/workflows/compositions.py tests/test_compositions.py
git commit -m "feat(deep-clean): compose deep_clean workflow from new phases"
```

---

### Task 12: Agent Registry Updates

**Files:**
- Modify: `codemonkeys/core/agents/__init__.py`
- Test: `tests/test_registry.py` (append)

- [ ] **Step 1: Write test for new registry entries**

Add to `tests/test_registry.py`:

```python
class TestDeepCleanAgentRegistration:
    def test_characterization_tester_registered(self) -> None:
        from codemonkeys.core.agents import default_registry

        registry = default_registry()
        spec = registry.get("python-characterization-tester")
        assert spec is not None
        assert spec.role.value == "executor"

    def test_structural_refactorer_registered(self) -> None:
        from codemonkeys.core.agents import default_registry

        registry = default_registry()
        spec = registry.get("python-structural-refactorer")
        assert spec is not None
        assert spec.role.value == "executor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py::TestDeepCleanAgentRegistration -v`
Expected: FAIL (agents not yet registered)

- [ ] **Step 3: Update __init__.py with new registrations**

Add to the `default_registry()` function in `codemonkeys/core/agents/__init__.py`:

```python
    from codemonkeys.core.agents.python_characterization_tester import (
        make_python_characterization_tester,
    )
    from codemonkeys.core.agents.python_structural_refactorer import (
        make_python_structural_refactorer,
    )
    from codemonkeys.artifacts.schemas.coverage import CoverageResult
    from codemonkeys.artifacts.schemas.refactor import CharTestResult, StructuralRefactorResult
    from codemonkeys.artifacts.schemas.structural import StructuralReport

    registry.register(
        AgentSpec(
            name="python-characterization-tester",
            role=AgentRole.EXECUTOR,
            description="Write characterization tests for uncovered source files",
            scope="file",
            produces=CharTestResult,
            consumes=CoverageResult,
            make=make_python_characterization_tester,
        )
    )
    registry.register(
        AgentSpec(
            name="python-structural-refactorer",
            role=AgentRole.EXECUTOR,
            description="Execute scoped structural refactoring (cycles, layering, splitting, naming)",
            scope="file",
            produces=StructuralRefactorResult,
            consumes=StructuralReport,
            make=make_python_structural_refactorer,
        )
    )
```

Also update `__all__` and the `__getattr__` function to include `make_python_characterization_tester` and `make_python_structural_refactorer`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_registry.py::TestDeepCleanAgentRegistration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/agents/__init__.py tests/test_registry.py
git commit -m "feat(deep-clean): register characterization tester and structural refactorer agents"
```

---

### Task 13: CLI Wiring — --deep-clean Flag

**Files:**
- Modify: `codemonkeys/run_review.py`
- Test: manual CLI verification

- [ ] **Step 1: Add --deep-clean arg to parser**

In `codemonkeys/run_review.py`, add to the `scope` mutually exclusive group:

```python
scope.add_argument(
    "--deep-clean",
    action="store_true",
    help="Deep clean — stabilize, write characterization tests, and refactor the codebase",
)
```

- [ ] **Step 2: Update _resolve_mode**

```python
def _resolve_mode(args: argparse.Namespace) -> str:
    if args.files:
        return "files"
    if args.diff:
        return "diff"
    if args.repo:
        return "repo"
    if args.deep_clean:
        return "deep_clean"
    return _select_mode()
```

- [ ] **Step 3: Update _pick_workflow**

```python
def _pick_workflow(config: ReviewConfig):
    if config.mode == "files":
        return make_files_workflow(auto_fix=config.auto_fix)
    if config.mode == "diff":
        return make_diff_workflow(auto_fix=config.auto_fix)
    if config.mode == "post_feature":
        return make_post_feature_workflow(auto_fix=config.auto_fix)
    if config.mode == "deep_clean":
        from codemonkeys.workflows.compositions import make_deep_clean_workflow
        return make_deep_clean_workflow()
    return make_full_repo_workflow(auto_fix=config.auto_fix)
```

- [ ] **Step 4: Update _handle_triage_gate for refactor gates**

The existing triage gate handler only handles the triage phase. For deep-clean, refactor gates need a different prompt. Update the `on_waiting` handler:

```python
def on_waiting(_: EventType, payload: object) -> None:
    phase_name = getattr(payload, "phase", "")
    if phase_name.startswith("refactor_"):
        _handle_refactor_gate(engine, display, phase_name)
    else:
        _handle_triage_gate(engine, display)
```

Add the new handler:

```python
def _handle_refactor_gate(
    engine: WorkflowEngine, display: WorkflowDisplay, phase_name: str
) -> None:
    display.pause()
    step_label = phase_name.replace("refactor_", "").replace("_", " ").title()
    console.print(
        Panel(
            f"[bold]Refactor Step: {step_label}[/bold]\n\n"
            '  [dim]"approve" to proceed with this refactoring[/dim]\n'
            '  [dim]"skip" to skip this step[/dim]',
            border_style="yellow",
            padding=(1, 2),
        )
    )
    user_input = console.input("  [bold]>[/bold] ").strip()
    display.resume()

    if not user_input or user_input.lower() == "skip":
        engine.resolve_gate("skip")
    else:
        engine.resolve_gate("approve")
```

- [ ] **Step 5: Run lint + typecheck**

Run: `uv run ruff check --fix codemonkeys/run_review.py && uv run ruff format codemonkeys/run_review.py`
Run: `uv run pyright codemonkeys/run_review.py`
Expected: No errors

- [ ] **Step 6: Verify CLI help shows --deep-clean**

Run: `uv run python -m codemonkeys.run_review --help`
Expected: Output includes `--deep-clean` with its help text

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/run_review.py
git commit -m "feat(deep-clean): wire --deep-clean CLI flag with refactor gate handler"
```

---

### Task 14: Lint, Typecheck, Full Test Suite

**Files:**
- All files from Tasks 1-13

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check --fix . && uv run ruff format .`
Expected: Clean or only auto-fixable issues

- [ ] **Step 2: Run pyright**

Run: `uv run pyright .`
Expected: No new errors (pre-existing errors may exist)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (existing + new)

- [ ] **Step 4: Fix any failures**

If any tests fail, fix the root cause (not the test assertion). Re-run until green.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: lint and typecheck fixes for deep-clean workflow"
```
