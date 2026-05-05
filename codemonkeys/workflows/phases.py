"""Phase types, workflow definitions, and execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class PhaseType(Enum):
    AUTOMATED = "automated"
    INTERACTIVE = "interactive"
    GATE = "gate"


@dataclass
class Phase:
    name: str
    phase_type: PhaseType
    execute: Callable[[WorkflowContext], Coroutine[Any, Any, Any]]


@dataclass
class Workflow:
    name: str
    phases: list[Phase]


@dataclass
class WorkflowContext:
    cwd: str
    run_id: str
    phase_results: dict[str, Any] = field(default_factory=dict)
    user_input: Any = None
    config: Any = None
