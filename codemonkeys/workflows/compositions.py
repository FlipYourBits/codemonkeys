"""Review workflow compositions — config and workflow builders for each review mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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
