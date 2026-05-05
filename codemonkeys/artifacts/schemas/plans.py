"""Schemas for feature and bugfix plans."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    description: str = Field(description="What this step accomplishes")
    files: list[str] = Field(
        default_factory=list,
        description="Files that will be created or modified in this step",
    )


class FeaturePlan(BaseModel):
    title: str = Field(description="Short title for the feature or bugfix")
    description: str = Field(
        description="Detailed description of what to build and why"
    )
    steps: list[PlanStep] = Field(description="Ordered implementation steps")
