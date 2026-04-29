from __future__ import annotations

from codemonkeys.graphs.python.check import build_pipeline
from codemonkeys.nodes.base import Verbosity


class TestBuildPipeline:
    def test_builds_with_defaults(self):
        p = build_pipeline("/tmp/repo")
        assert len(p._ordered_names) > 0
        assert p.working_dir == "/tmp/repo"

    def test_custom_base_ref(self):
        p = build_pipeline("/tmp/repo", base_ref="develop")
        assert len(p._ordered_names) > 0

    def test_verbosity_passed_through(self):
        p = build_pipeline("/tmp/repo", verbosity=Verbosity.verbose)
        assert p.verbosity == Verbosity.verbose

    def test_steps_are_correct_sequence(self):
        p = build_pipeline("/tmp/repo")
        names = p._ordered_names
        assert names[0] == "python_ensure_tools"
        assert names[1] == "python_lint"
        assert names[2] == "python_format"
        assert "python_test" in names
        assert "python_code_review" in names
        assert "python_security_audit" in names
        assert "docs_review" in names
        assert "python_dependency_audit" in names
        assert "resolve_findings" in names
        assert names[-1] == "python_lint_2"

    def test_parallel_steps_present(self):
        p = build_pipeline("/tmp/repo")
        parallel_step = p._resolved[3]
        assert isinstance(parallel_step, list)
        parallel_names = [name for name, _ in parallel_step]
        assert "python_test" in parallel_names
        assert "python_code_review" in parallel_names
        assert "python_security_audit" in parallel_names
