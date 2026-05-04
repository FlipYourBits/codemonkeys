"""Tests for branch_guard hook — protected branch detection and branch name inference."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "branch_guard.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestInferBranchName:
    """Test the inference logic by importing the module directly."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("branch_guard", HOOK)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_fix_prefix(self):
        assert self.mod._infer_branch_name("fix the login bug on settings page") == "fix/login-bug-settings-page"

    def test_feat_prefix_default(self):
        assert self.mod._infer_branch_name("add user authentication with OAuth") == "feat/add-user-authentication-oauth"

    def test_refactor_prefix(self):
        assert self.mod._infer_branch_name("refactor the database connection pooling") == "refactor/database-connection-pooling"

    def test_docs_prefix(self):
        assert self.mod._infer_branch_name("docs update README") == "docs/update-readme"

    def test_chore_prefix(self):
        assert self.mod._infer_branch_name("chore clean up old migrations") == "chore/clean-up-old-migrations"

    def test_test_prefix(self):
        assert self.mod._infer_branch_name("test add coverage for auth module") == "test/add-coverage-auth-module"

    def test_skill_trigger_stripped(self):
        assert self.mod._infer_branch_name("/codemonkeys:python-feature add caching layer") == "feat/add-caching-layer"

    def test_multiple_skill_triggers_stripped(self):
        assert self.mod._infer_branch_name("/foo:bar /baz:qux fix the thing") == "fix/thing"

    def test_empty_prompt(self):
        assert self.mod._infer_branch_name("") == "feat/unnamed-branch"

    def test_only_noise_words(self):
        assert self.mod._infer_branch_name("the a an to for") == "feat/unnamed-branch"

    def test_only_skill_trigger(self):
        assert self.mod._infer_branch_name("/codemonkeys:python-feature") == "feat/unnamed-branch"

    def test_slug_capped_at_50_chars(self):
        long_prompt = "add " + " ".join(f"word{i}" for i in range(30))
        result = self.mod._infer_branch_name(long_prompt)
        slug = result.split("/", 1)[1]
        assert len(slug) <= 50

    def test_special_characters_replaced(self):
        assert self.mod._infer_branch_name("fix bug #123 in auth/login module") == "fix/bug-123-auth-login-module"

    def test_bug_maps_to_fix(self):
        assert self.mod._infer_branch_name("bug in the payment processor") == "fix/payment-processor"

    def test_hotfix_maps_to_fix(self):
        assert self.mod._infer_branch_name("hotfix crash on startup") == "fix/crash-startup"

    def test_ci_maps_to_chore(self):
        assert self.mod._infer_branch_name("ci update github actions workflow") == "chore/update-github-actions-workflow"

    def test_build_maps_to_chore(self):
        assert self.mod._infer_branch_name("build update webpack config") == "chore/update-webpack-config"
