"""Core data structures."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(frozen=True)
class AgentDefinition:
    """Immutable description of an agent to run."""

    name: str
    model: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    output_schema: type[BaseModel] | None = None


@dataclass
class TokenUsage:
    """Token accounting from a single agent run."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class RunResult:
    """Result returned by run_agent()."""

    output: BaseModel | None
    text: str
    usage: TokenUsage
    cost_usd: float
    duration_ms: int
    error: str | None = None
