"""Schemas for refactoring and characterization test results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CharTestResult(BaseModel):
    tests_written: list[str] = Field(description="Paths to newly created test files")
    files_covered: list[str] = Field(
        description="Source files now covered by characterization tests"
    )
    coverage_after: float | None = Field(
        description="Re-measured coverage percentage, or null"
    )


class StructuralRefactorResult(BaseModel):
    files_changed: list[str] = Field(description="Files that were modified or created")
    description: str = Field(description="What structural change was made")
    tests_passed: bool = Field(
        description="Whether scoped tests passed after the change"
    )
