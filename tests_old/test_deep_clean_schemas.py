from __future__ import annotations

from codemonkeys.artifacts.schemas.coverage import CoverageResult, FileCoverage
from codemonkeys.artifacts.schemas.health import (
    BuildCheckResult,
    DependencyHealthResult,
    OutdatedPackage,
)
from codemonkeys.artifacts.schemas.refactor import (
    CharTestResult,
    StructuralRefactorResult,
)
from codemonkeys.artifacts.schemas.structural import (
    FileMetrics,
    HotFile,
    LayerViolation,
    NamingIssue,
    StructuralReport,
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
