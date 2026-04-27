from __future__ import annotations

from langclaude.graphs.python_quality_gate import build_pipeline
from langclaude.models import HAIKU_4_5, SONNET_4_6
from langclaude.nodes.base import Verbosity


class TestBuildPipeline:
    def test_builds_with_default_diff_mode(self):
        p = build_pipeline("/tmp/repo")
        assert len(p._ordered_names) > 0
        assert p.working_dir == "/tmp/repo"
        assert p.config["code_review"]["mode"] == "diff"

    def test_builds_with_full_mode(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert len(p._ordered_names) > 0
        assert p.working_dir == "/tmp/repo"

    def test_builds_with_diff_mode(self):
        p = build_pipeline("/tmp/repo", mode="diff", base_ref="develop")
        assert len(p._ordered_names) > 0
        assert p.extra_state.get("base_ref") == "develop"

    def test_full_mode_no_mode_overrides(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "mode" not in p.config.get("code_review", {})
        assert p.extra_state == {"base_ref": "main"}

    def test_diff_mode_sets_config_overrides(self):
        p = build_pipeline("/tmp/repo", mode="diff")
        assert p.config["python_coverage"]["mode"] == "diff"
        assert p.config["code_review"]["mode"] == "diff"
        assert p.config["security_audit"]["mode"] == "diff"
        assert p.config["docs_review"]["mode"] == "diff"

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
            [
                "python_test",
                "python_coverage",
                "code_review",
                "security_audit",
                "docs_review",
                "python_dependency_audit",
            ],
            "resolve_findings",
            "python_lint",
        ]

    def test_parallel_steps_present(self):
        p = build_pipeline("/tmp/repo", mode="full")
        parallel = p.steps[2]
        assert isinstance(parallel, list)
        assert "python_test" in parallel
        assert "code_review" in parallel
        assert "security_audit" in parallel

    def test_resolve_findings_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "resolve_findings" in p.config
        requires = p.config["resolve_findings"]["requires"]
        assert "code_review" in requires
        assert "security_audit" in requires
        assert "docs_review" in requires
        assert "python_dependency_audit" in requires
        assert "python_test" in requires
        assert "python_coverage" in requires

    def test_resolve_findings_interactive_by_default(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.config["resolve_findings"]["interactive"] is True

    def test_no_interactive_flag(self):
        p = build_pipeline("/tmp/repo", mode="full", interactive=False)
        assert p.config["resolve_findings"]["interactive"] is False

    def test_python_lint_2_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "python_lint_2" in p.config
        assert p.config["python_lint_2"]["requires"] == ["python_lint"]


class TestTokenReduction:
    def test_cheap_nodes_use_sonnet(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.config["python_test"]["model"] == SONNET_4_6
        assert p.config["python_coverage"]["model"] == SONNET_4_6
        assert p.config["docs_review"]["model"] == SONNET_4_6

    def test_dep_audit_uses_haiku(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.config["python_dependency_audit"]["model"] == HAIKU_4_5

    def test_review_nodes_use_default_model(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "model" not in p.config["code_review"]
        assert "model" not in p.config["security_audit"]
        assert "model" not in p.config["resolve_findings"]

    def test_all_agent_nodes_have_max_turns(self):
        p = build_pipeline("/tmp/repo", mode="full")
        for name in (
            "python_test", "python_coverage", "code_review",
            "security_audit", "docs_review", "python_dependency_audit",
            "resolve_findings",
        ):
            assert "max_turns" in p.config[name], f"{name} missing max_turns"

    def test_all_agent_nodes_have_budget(self):
        p = build_pipeline("/tmp/repo", mode="full")
        for name in (
            "python_test", "python_coverage", "code_review",
            "security_audit", "docs_review", "python_dependency_audit",
            "resolve_findings",
        ):
            assert "max_budget_usd" in p.config[name], f"{name} missing budget"
