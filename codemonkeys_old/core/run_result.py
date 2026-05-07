"""Result dataclass returned by AgentRunner.run_agent()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RunResult:
    text: str
    structured: dict[str, Any] | None
    usage: dict[str, Any]
    cost: float | None
    duration_ms: int
