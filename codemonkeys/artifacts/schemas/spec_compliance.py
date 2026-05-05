"""Schemas for spec compliance review findings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SpecComplianceFinding(BaseModel):
    category: Literal[
        "completeness",
        "scope_creep",
        "contract_compliance",
        "behavioral_fidelity",
        "test_coverage",
    ] = Field(description="Which aspect of spec compliance this finding addresses")
    severity: Literal["high", "medium", "low"] = Field(
        description="Impact severity — high: missing feature, medium: partial, low: minor gap"
    )
    spec_step: str | None = Field(
        description="Which plan step this relates to, or null for general findings"
    )
    files: list[str] = Field(description="Affected file paths")
    title: str = Field(description="Short one-line summary")
    description: str = Field(description="Detailed explanation")
    suggestion: str | None = Field(default=None, description="How to resolve the gap")


class SpecComplianceFindings(BaseModel):
    spec_title: str = Field(description="Title of the spec/plan being reviewed")
    steps_implemented: int = Field(
        description="Number of spec steps that were implemented"
    )
    steps_total: int = Field(description="Total number of spec steps")
    findings: list[SpecComplianceFinding] = Field(
        default_factory=list,
        description="Spec compliance issues found",
    )
