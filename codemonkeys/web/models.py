"""Pydantic models for the web API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class AgentInfo(BaseModel):
    key: str
    description: str
    model: str | None = None
    needs_prompt: bool = False
    default_prompt: str = ""


class RunRequest(BaseModel):
    agent_key: str
    prompt: str = ""
    context_files: list[str] = []
    token_budget: int = 100_000


class ChatStartRequest(BaseModel):
    agent_key: str
    message: str
    context_files: list[str] = []
    token_budget: int = 200_000


class CwdUpdate(BaseModel):
    path: str


class ChatMessageRequest(BaseModel):
    message: str


class SessionStatus(BaseModel):
    session_id: str
    mode: Literal["run", "chat"]
    agent_key: str
    status: Literal["idle", "running", "completed", "failed", "cancelled"]
    prompt: str
    created_at: str
    completed_at: str | None = None
    cost_usd: float | None = None
    total_tokens: int = 0
    token_budget: int = 100_000
    output_file: str | None = None


class SavedOutput(BaseModel):
    filename: str
    agent_key: str
    created_at: str
    size_bytes: int


class WSEvent(BaseModel):
    type: str
    session_id: str
    data: dict[str, Any] = {}
