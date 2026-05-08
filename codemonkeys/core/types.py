"""Core data structures."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def json_safe(obj: Any) -> Any:
    """Recursively convert any object to a JSON-serializable form."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[union-attr]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: json_safe(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    if hasattr(obj, "__dict__"):
        return {k: json_safe(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return repr(obj)


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
    agent_def: AgentDefinition | None = None
    events: list = field(default_factory=list)

    def save_output(self, directory: str | Path) -> Path | None:
        """Write structured output JSON to directory. Returns path or None."""
        if self.output is None or self.agent_def is None:
            return None
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w\-.]", "_", self.agent_def.name)
        path = directory / f"{name}.json"
        path.write_text(self.output.model_dump_json(indent=2) + "\n")
        return path
