"""Schemas for real code coverage measurement results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileCoverage(BaseModel):
    lines_covered: int = Field(description="Number of executed lines")
    lines_missed: int = Field(description="Number of unexecuted lines")
    percent: float = Field(description="Line coverage percentage")


class CoverageResult(BaseModel):
    overall_percent: float = Field(description="Overall line coverage percentage")
    per_file: dict[str, FileCoverage] = Field(description="Per-file coverage breakdown")
    uncovered_files: list[str] = Field(description="Files below the coverage threshold")
