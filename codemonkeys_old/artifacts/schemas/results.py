"""Schemas for fix and verification results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FixResult(BaseModel):
    file: str = Field(description="Relative path to the file that was fixed")
    fixed: list[str] = Field(
        default_factory=list,
        description="Descriptions of findings that were successfully fixed",
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="Descriptions of findings that could not be fixed, with reasons",
    )


class VerificationResult(BaseModel):
    tests_passed: bool = Field(description="Whether pytest passed")
    lint_passed: bool = Field(description="Whether ruff check passed")
    typecheck_passed: bool = Field(description="Whether pyright passed")
    errors: list[str] = Field(
        default_factory=list,
        description="Specific error messages from failed checks",
    )
