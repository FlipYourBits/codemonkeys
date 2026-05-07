"""Schemas for agent audit results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Issue(BaseModel):
    category: Literal[
        "unauthorized_tool",
        "inappropriate_tool_use",
        "repeated_tool_call",
        "wasted_turn",
        "off_task",
        "instruction_violation",
        "output_problem",
    ] = Field(description="Type of issue found in the agent's behavior")
    turn: int | None = Field(
        description="Which assistant turn the issue occurred on, or null if general"
    )
    description: str = Field(description="What happened")
    evidence: str = Field(
        description="Quote from thinking block, tool call, or output that demonstrates the issue"
    )


class AgentAudit(BaseModel):
    agent_name: str = Field(description="Name of the agent that was audited")
    verdict: Literal["pass", "fail"] = Field(
        description="pass if agent behaved correctly, fail if instruction violations or off-task behavior"
    )
    summary: str = Field(
        description="2-3 sentence narrative of what the agent did and how well it performed"
    )
    issues: list[Issue] = Field(
        default_factory=list,
        description="Specific issues found, empty if verdict is pass",
    )
    token_assessment: str = Field(
        description="Brief assessment of whether token usage was reasonable for the task"
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggestions for improving the agent's prompt or configuration",
    )
