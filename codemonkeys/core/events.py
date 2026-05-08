"""Typed events emitted during agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from codemonkeys.core.types import RunResult, TokenUsage


@dataclass
class Event:
    """Base event. All events carry agent_name and timestamp."""

    agent_name: str
    timestamp: float


@dataclass
class AgentStarted(Event):
    """Emitted when an agent run begins."""

    model: str


@dataclass
class ToolCall(Event):
    """Emitted when the agent invokes a tool."""

    tool_name: str
    tool_input: dict


@dataclass
class ToolResult(Event):
    """Emitted when a tool returns a result."""

    tool_name: str
    output: str


@dataclass
class ToolDenied(Event):
    """Emitted when a tool call is blocked by the allowlist."""

    tool_name: str
    command: str


@dataclass
class TokenUpdate(Event):
    """Emitted on each assistant message with updated usage."""

    usage: TokenUsage
    cost_usd: float


@dataclass
class AgentCompleted(Event):
    """Emitted when an agent finishes successfully."""

    result: RunResult


@dataclass
class AgentError(Event):
    """Emitted when an agent fails."""

    error: str


@dataclass
class ThinkingOutput(Event):
    """Emitted when the agent produces thinking content."""

    text: str


@dataclass
class TextOutput(Event):
    """Emitted when the agent produces text output."""

    text: str


@dataclass
class RawMessage(Event):
    """Wraps every raw SDK message for full-fidelity logging."""

    message_type: str
    data: dict


@dataclass
class RateLimitHit(Event):
    """Emitted when the SDK reports a rate limit."""

    rate_limit_type: str
    status: str
    wait_seconds: int


EventHandler = Callable[[Event], None]


class EventCollector:
    """Handler that accumulates events into a list."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)
