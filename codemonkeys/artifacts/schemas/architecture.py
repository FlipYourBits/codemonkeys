"""Schemas for cross-file architecture review findings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ArchitectureFinding(BaseModel):
    files: list[str] = Field(
        description="Relative paths to all files involved in this finding"
    )
    severity: Literal["high", "medium", "low"] = Field(
        description="Impact severity — high: architectural flaw, medium: should address, low: suggestion"
    )
    category: Literal["design"] = Field(
        description="Finding category — always 'design' for architecture findings"
    )
    subcategory: str = Field(
        description="Specific check that triggered this finding (e.g., 'paradigm_inconsistency', 'layer_violation')"
    )
    title: str = Field(description="Short one-line summary of the issue")
    description: str = Field(
        description="Detailed explanation of the cross-file issue and why it matters"
    )
    suggestion: str | None = Field(
        default=None,
        description="Concrete suggestion for how to resolve the issue",
    )


class ArchitectureFindings(BaseModel):
    files_reviewed: list[str] = Field(
        description="All files the architecture reviewer examined"
    )
    findings: list[ArchitectureFinding] = Field(
        default_factory=list,
        description="Cross-file design issues found, empty if architecture is clean",
    )
