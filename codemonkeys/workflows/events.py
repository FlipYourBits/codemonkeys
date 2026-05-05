"""Typed event system for workflow-to-UI communication."""

from __future__ import annotations

from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field


class EventType(Enum):
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    AGENT_STARTED = "agent_started"
    AGENT_PROGRESS = "agent_progress"
    AGENT_COMPLETED = "agent_completed"
    FINDING_ADDED = "finding_added"
    WAITING_FOR_USER = "waiting_for_user"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ERROR = "workflow_error"


class PhaseStartedPayload(BaseModel):
    phase: str = Field(description="Name of the phase that started")
    workflow: str = Field(description="Name of the workflow")


class PhaseCompletedPayload(BaseModel):
    phase: str = Field(description="Name of the phase that completed")
    workflow: str = Field(description="Name of the workflow")


class AgentStartedPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent that started")
    task_id: str = Field(description="Unique ID for this agent task")


class AgentProgressPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent")
    task_id: str = Field(description="Unique ID for this agent task")
    tokens: int = Field(default=0, description="Tokens consumed so far")
    tool_calls: int = Field(default=0, description="Number of tool calls so far")
    current_tool: str = Field(default="", description="Currently executing tool")


class AgentCompletedPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent that completed")
    task_id: str = Field(description="Unique ID for this agent task")
    tokens: int = Field(default=0, description="Total tokens consumed")


class FindingAddedPayload(BaseModel):
    file: str = Field(description="File the finding belongs to")
    severity: str = Field(description="Finding severity")
    title: str = Field(description="Finding title")


class WaitingForUserPayload(BaseModel):
    phase: str = Field(description="Phase that is waiting for user input")
    workflow: str = Field(description="Name of the workflow")


class WorkflowCompletedPayload(BaseModel):
    workflow: str = Field(description="Name of the workflow that completed")
    run_id: str = Field(description="Artifact store run ID")


class WorkflowErrorPayload(BaseModel):
    workflow: str = Field(description="Name of the workflow that errored")
    error: str = Field(description="Error message")


EventCallback = Callable[[EventType, BaseModel], None]


class EventEmitter:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventCallback]] = {}
        self._wildcard_handlers: list[EventCallback] = []

    def on(self, event_type: EventType, callback: EventCallback) -> None:
        self._handlers.setdefault(event_type, []).append(callback)

    def on_any(self, callback: EventCallback) -> None:
        self._wildcard_handlers.append(callback)

    def emit(self, event_type: EventType, payload: BaseModel) -> None:
        for handler in self._handlers.get(event_type, []):
            handler(event_type, payload)
        for handler in self._wildcard_handlers:
            handler(event_type, payload)
