from __future__ import annotations

from langclaude.graphs.python_quality_gate import build_pipeline
from langclaude.nodes.base import Verbosity


class TestBuildPipeline:
    def test_builds_with_default_diff_mode(self):
        p = build_pipeline("/tmp/repo")
        assert p._app is not None
        assert p.working_dir == "/tmp/repo"
        assert p.config.get("code_review") == {"mode": "diff"}

    def test_builds_with_full_mode(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p._app is not None
        assert p.working_dir == "/tmp/repo"

    def test_builds_with_diff_mode(self):
        p = build_pipeline("/tmp/repo", mode="diff", base_ref="develop")
        assert p._app is not None
        assert p.extra_state.get("base_ref") == "develop"

    def test_full_mode_no_mode_overrides(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "code_review" not in p.config or "mode" not in p.config.get("code_review", {})
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
            "python_coverage",
            "python_test",
            "python_dependency_audit",
            "code_review",
            "security_audit",
            "docs_review",
            "resolve_findings",
            "python_lint",
        ]

    def test_resolve_findings_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "resolve_findings" in p.config
        assert p.config["resolve_findings"]["requires"] == [
            "code_review",
            "security_audit",
            "docs_review",
            "python_dependency_audit",
        ]

    def test_python_lint_2_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "python_lint_2" in p.config
        assert p.config["python_lint_2"]["requires"] == ["python_lint"]
