"""Review workflow compositions — config and workflow builders for each review mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from codemonkeys.workflows.phase_library import (
    architecture_review,
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
    doc_review,
    file_review,
    fix,
    mechanical_audit,
    report,
    spec_compliance_review,
    triage,
    verify,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow

ALL_TOOLS = frozenset(
    {"ruff", "pyright", "pytest", "pip_audit", "secrets", "coverage", "dead_code"}
)
SCOPED_TOOLS = frozenset({"ruff", "pyright", "pytest", "secrets", "coverage"})

_MODE_TOOLS: dict[str, frozenset[str]] = {
    "full_repo": ALL_TOOLS,
    "diff": SCOPED_TOOLS,
    "files": SCOPED_TOOLS,
    "post_feature": SCOPED_TOOLS,
}


@dataclass
class ReviewConfig:
    mode: Literal["full_repo", "diff", "files", "post_feature"]
    target_files: list[str] | None = None
    spec_path: str | None = None
    auto_fix: bool = False
    max_concurrent: int = 5
    base_branch: str = "main"
    audit_tools: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.audit_tools:
            self.audit_tools = set(_MODE_TOOLS[self.mode])


def make_full_repo_workflow(*, auto_fix: bool = False) -> Workflow:
    """Full repository review — all files, all tools, all reviewers."""
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="full_repo_review",
        phases=[
            Phase(
                name="discover",
                phase_type=PhaseType.AUTOMATED,
                execute=discover_all_files,
            ),
            Phase(
                name="mechanical_audit",
                phase_type=PhaseType.AUTOMATED,
                execute=mechanical_audit,
            ),
            Phase(
                name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review
            ),
            Phase(
                name="architecture_review",
                phase_type=PhaseType.AUTOMATED,
                execute=architecture_review,
            ),
            Phase(
                name="doc_review", phase_type=PhaseType.AUTOMATED, execute=doc_review
            ),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_diff_workflow(*, auto_fix: bool = False) -> Workflow:
    """Diff review — changed files on branch, no doc review."""
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="diff_review",
        phases=[
            Phase(
                name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_diff
            ),
            Phase(
                name="mechanical_audit",
                phase_type=PhaseType.AUTOMATED,
                execute=mechanical_audit,
            ),
            Phase(
                name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review
            ),
            Phase(
                name="architecture_review",
                phase_type=PhaseType.AUTOMATED,
                execute=architecture_review,
            ),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_files_workflow(*, auto_fix: bool = False) -> Workflow:
    """Files review — user-specified files only, no architecture or doc review."""
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="files_review",
        phases=[
            Phase(
                name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_files
            ),
            Phase(
                name="mechanical_audit",
                phase_type=PhaseType.AUTOMATED,
                execute=mechanical_audit,
            ),
            Phase(
                name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review
            ),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_post_feature_workflow(*, auto_fix: bool = False) -> Workflow:
    """Post-feature review — spec compliance, hardening, full doc check."""
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="post_feature_review",
        phases=[
            Phase(
                name="discover",
                phase_type=PhaseType.AUTOMATED,
                execute=discover_from_spec,
            ),
            Phase(
                name="mechanical_audit",
                phase_type=PhaseType.AUTOMATED,
                execute=mechanical_audit,
            ),
            Phase(
                name="spec_compliance_review",
                phase_type=PhaseType.AUTOMATED,
                execute=spec_compliance_review,
            ),
            Phase(
                name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review
            ),
            Phase(
                name="architecture_review",
                phase_type=PhaseType.AUTOMATED,
                execute=architecture_review,
            ),
            Phase(
                name="doc_review", phase_type=PhaseType.AUTOMATED, execute=doc_review
            ),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )
