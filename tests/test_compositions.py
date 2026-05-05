from __future__ import annotations

from codemonkeys.workflows.compositions import ReviewConfig


class TestReviewConfig:
    def test_full_repo_config(self) -> None:
        config = ReviewConfig(mode="full_repo")
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "pip_audit",
            "secrets",
            "coverage",
            "dead_code",
        }
        assert config.auto_fix is False
        assert config.max_concurrent == 5
        assert config.base_branch == "main"

    def test_diff_config(self) -> None:
        config = ReviewConfig(mode="diff")
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
        }
        assert "pip_audit" not in config.audit_tools

    def test_files_config(self) -> None:
        config = ReviewConfig(mode="files", target_files=["a.py", "b.py"])
        assert config.target_files == ["a.py", "b.py"]
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
        }

    def test_post_feature_config(self) -> None:
        config = ReviewConfig(mode="post_feature", spec_path="docs/plan.md")
        assert config.spec_path == "docs/plan.md"
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
        }

    def test_auto_fix_override(self) -> None:
        config = ReviewConfig(mode="diff", auto_fix=True)
        assert config.auto_fix is True

    def test_custom_base_branch(self) -> None:
        config = ReviewConfig(mode="diff", base_branch="develop")
        assert config.base_branch == "develop"

    def test_custom_audit_tools(self) -> None:
        config = ReviewConfig(mode="diff", audit_tools={"ruff"})
        assert config.audit_tools == {"ruff"}
