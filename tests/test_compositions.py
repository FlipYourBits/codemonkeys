from __future__ import annotations

from codemonkeys.workflows.compositions import (
    ReviewConfig,
    make_diff_workflow,
    make_files_workflow,
    make_full_repo_workflow,
    make_post_feature_workflow,
)
from codemonkeys.workflows.phases import PhaseType


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
            "license_compliance",
            "release_hygiene",
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
            "license_compliance",
            "release_hygiene",
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
            "license_compliance",
            "release_hygiene",
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
            "license_compliance",
            "release_hygiene",
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

    def test_full_repo_includes_new_tools(self) -> None:
        config = ReviewConfig(mode="full_repo")
        assert "license_compliance" in config.audit_tools
        assert "release_hygiene" in config.audit_tools

    def test_diff_includes_new_tools(self) -> None:
        config = ReviewConfig(mode="diff")
        assert "license_compliance" in config.audit_tools
        assert "release_hygiene" in config.audit_tools


class TestFullRepoWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_full_repo_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "architecture_review",
            "doc_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_triage_is_gate(self) -> None:
        workflow = make_full_repo_workflow()
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE

    def test_auto_fix_triage_is_automated(self) -> None:
        workflow = make_full_repo_workflow(auto_fix=True)
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.AUTOMATED


class TestDiffWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_diff_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "architecture_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_no_doc_review(self) -> None:
        workflow = make_diff_workflow()
        names = [p.name for p in workflow.phases]
        assert "doc_review" not in names


class TestFilesWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_files_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_no_architecture_or_doc_review(self) -> None:
        workflow = make_files_workflow()
        names = [p.name for p in workflow.phases]
        assert "architecture_review" not in names
        assert "doc_review" not in names


class TestPostFeatureWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_post_feature_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "spec_compliance_review",
            "file_review",
            "architecture_review",
            "doc_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_spec_compliance_before_file_review(self) -> None:
        workflow = make_post_feature_workflow()
        names = [p.name for p in workflow.phases]
        assert names.index("spec_compliance_review") < names.index("file_review")


class TestDeepCleanWorkflow:
    def test_deep_clean_workflow_has_expected_phases(self) -> None:
        from codemonkeys.workflows.compositions import make_deep_clean_workflow

        wf = make_deep_clean_workflow()
        names = [p.name for p in wf.phases]

        assert "build_check" in names
        assert "dependency_health" in names
        assert "coverage" in names
        assert "structural_analysis" in names
        assert "characterization_tests" in names

        refactor_names = [n for n in names if n.startswith("refactor_")]
        assert len(refactor_names) == 6

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
                assert phase.phase_type == PhaseType.GATE, (
                    f"{phase.name} should be GATE"
                )

    def test_deep_clean_config(self) -> None:
        from codemonkeys.workflows.compositions import ReviewConfig

        config = ReviewConfig(mode="deep_clean")
        assert "dead_code" in config.audit_tools
        assert "pip_audit" in config.audit_tools
        assert "license_compliance" in config.audit_tools
        assert "release_hygiene" in config.audit_tools
