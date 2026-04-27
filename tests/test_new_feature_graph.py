"""Tests for graphs/python_new_feature.py build_pipeline."""

from __future__ import annotations

from agentpipe.graphs.python_new_feature import build_pipeline
from agentpipe.nodes.base import Verbosity


class TestNewFeatureBuildPipeline:
    def test_builds_successfully(self):
        p = build_pipeline("/tmp/repo", "add retry decorator")
        assert len(p._ordered_names) > 0
        assert p.working_dir == "/tmp/repo"
        assert p.task == "add retry decorator"

    def test_default_base_ref(self):
        p = build_pipeline("/tmp", "task")
        assert p.extra_state.get("base_ref") == "main"

    def test_custom_base_ref(self):
        p = build_pipeline("/tmp", "task", base_ref="develop")
        assert p.extra_state.get("base_ref") == "develop"

    def test_verbosity_passed(self):
        p = build_pipeline("/tmp", "task", verbosity=Verbosity.verbose)
        assert p.verbosity == Verbosity.verbose

    def test_steps_include_key_nodes(self):
        p = build_pipeline("/tmp", "task")
        assert "git_new_branch" in p.steps
        assert "python_plan_feature" in p.steps
        assert "python_implement_feature" in p.steps
        assert "git_commit" in p.steps

    def test_diff_mode_config(self):
        p = build_pipeline("/tmp", "task")
        assert p.config.get("code_review") == {"mode": "diff"}
        assert p.config.get("python_coverage") == {"mode": "diff"}
        assert p.config.get("security_audit") == {"mode": "diff"}
        assert p.config.get("docs_review") == {"mode": "diff"}
