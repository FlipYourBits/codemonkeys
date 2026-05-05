"""Schemas for code review findings and fix requests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    file: str = Field(description="Relative path to the file containing the issue")
    line: int | None = Field(
        description="Line number where the issue occurs, or null if file-level"
    )
    severity: Literal["high", "medium", "low", "info"] = Field(
        description="Impact severity — high: likely bug or vulnerability, medium: should fix, low: suggestion, info: observation"
    )
    category: Literal["quality", "security", "bug", "style", "changelog", "readme"] = (
        Field(description="Type of issue found")
    )
    subcategory: str = Field(
        description="Specific check that triggered this finding (e.g., 'injection', 'naming', 'missing_entry')"
    )
    title: str = Field(description="Short one-line summary of the issue")
    description: str = Field(
        description="Detailed explanation of what's wrong and why it matters"
    )
    suggestion: str | None = Field(
        default=None,
        description="Concrete suggestion for how to fix the issue, with example code if applicable",
    )


class FileFindings(BaseModel):
    file: str = Field(description="Relative path to the reviewed file")
    summary: str = Field(description="One sentence describing what this file does")
    findings: list[Finding] = Field(
        default_factory=list,
        description="List of issues found in this file, empty if the file is clean",
    )


class FixRequest(BaseModel):
    file: str = Field(description="Relative path to the file to fix")
    findings: list[Finding] = Field(
        description="Specific findings the fixer agent should address"
    )
