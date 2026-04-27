from __future__ import annotations

from langclaude.graphs.python_quality_gate import build_pipeline
from langclaude.nodes.base import Verbosity


class TestBuildPipeline:
    def test_builds_with_full_mode(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p._app is not None
        assert p.working_dir == "/tmp/repo"

    def test_builds_with_diff_mode(self):
        p = build_pipeline("/tmp/repo", mode="diff", base_ref="develop")
        assert p._app is not None
        assert p.extra_state.get("base_ref") == "develop"

    def test_full_mode_no_config_overrides(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.config == {}
        assert p.extra_state == {"base_ref": "main"}

    def test_diff_mode_sets_config_overrides(self):
        p = build_pipeline("/tmp/repo", mode="diff")
        assert p.config.get("python_coverage") == {"mode": "diff"}
        assert p.config.get("code_review") == {"mode": "diff"}
        assert p.config.get("security_audit") == {"mode": "diff"}
        assert p.config.get("docs_review") == {"mode": "diff"}

    def test_diff_mode_default_base_ref(self):
        p = build_pipeline("/tmp/repo", mode="diff")
        assert p.extra_state.get("base_ref") == "main"

    def test_verbosity_passed_through(self):
        p = build_pipeline("/tmp/repo", mode="full", verbosity=Verbosity.verbose)
        assert p.verbosity == Verbosity.verbose

    def test_steps_are_correct_sequence(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.steps == [
            "python_lint",
            "python_format",
            "python_test",
            "python_coverage",
            "code_review",
            "security_audit",
            "docs_review",
            "dependency_audit",
            "python_lint",
        ]
