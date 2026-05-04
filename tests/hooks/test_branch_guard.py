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


class TestGetProtectedBranches:
    @pytest.fixture(autouse=True)
    def _import_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("branch_guard", HOOK)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_defaults_always_present(self, tmp_path):
        result = self.mod._get_protected_branches(tmp_path)
        assert "main" in result
        assert "master" in result

    def test_config_adds_extras(self, tmp_path):
        config_dir = tmp_path / ".codemonkeys"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"protected_branches": ["develop", "release"]}))
        result = self.mod._get_protected_branches(tmp_path)
        assert "main" in result
        assert "master" in result
        assert "develop" in result
        assert "release" in result

    def test_config_missing_key(self, tmp_path):
        config_dir = tmp_path / ".codemonkeys"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"sandbox": True}))
        result = self.mod._get_protected_branches(tmp_path)
        assert result == {"main", "master"}

    def test_config_file_missing(self, tmp_path):
        result = self.mod._get_protected_branches(tmp_path)
        assert result == {"main", "master"}

    def test_config_malformed_json(self, tmp_path):
        config_dir = tmp_path / ".codemonkeys"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("not json{{{")
        result = self.mod._get_protected_branches(tmp_path)
        assert result == {"main", "master"}

    def test_config_protected_branches_not_list(self, tmp_path):
        config_dir = tmp_path / ".codemonkeys"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"protected_branches": "develop"}))
        result = self.mod._get_protected_branches(tmp_path)
        assert result == {"main", "master"}


def _init_git_repo(path: Path, branch: str = "main") -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)


class TestHookFlow:
    def test_blocks_on_main(self, tmp_path):
        _init_git_repo(tmp_path, "main")
        result = run_hook({"prompt": "add a new feature", "cwd": str(tmp_path)})
        assert result.returncode != 0
        assert "protected branch" in result.stdout.lower()
        assert "git checkout -b" in result.stdout

    def test_blocks_on_master(self, tmp_path):
        _init_git_repo(tmp_path, "master")
        result = run_hook({"prompt": "fix something", "cwd": str(tmp_path)})
        assert result.returncode != 0
        assert "git checkout -b fix/" in result.stdout

    def test_allows_feature_branch(self, tmp_path):
        _init_git_repo(tmp_path, "main")
        subprocess.run(["git", "checkout", "-b", "feat/my-feature"], cwd=tmp_path, capture_output=True, check=True)
        result = run_hook({"prompt": "add a new feature", "cwd": str(tmp_path)})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_allows_non_git_dir(self, tmp_path):
        result = run_hook({"prompt": "add a new feature", "cwd": str(tmp_path)})
        assert result.returncode == 0

    def test_blocks_custom_protected_branch(self, tmp_path):
        _init_git_repo(tmp_path, "develop")
        config_dir = tmp_path / ".codemonkeys"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"protected_branches": ["develop"]}))
        result = run_hook({"prompt": "add a feature", "cwd": str(tmp_path)})
        assert result.returncode != 0
        assert "protected branch" in result.stdout.lower()

    def test_suggested_branch_in_output(self, tmp_path):
        _init_git_repo(tmp_path, "main")
        result = run_hook({"prompt": "fix the login bug", "cwd": str(tmp_path)})
        assert "git checkout -b fix/login-bug" in result.stdout

    def test_detached_head_allowed(self, tmp_path):
        _init_git_repo(tmp_path, "main")
        subprocess.run(["git", "checkout", "--detach"], cwd=tmp_path, capture_output=True, check=True)
        result = run_hook({"prompt": "add something", "cwd": str(tmp_path)})
        assert result.returncode == 0
