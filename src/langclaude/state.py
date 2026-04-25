"""Shared LangGraph state schema.

Nodes read what they need and return a partial dict; LangGraph merges it
into the running state.
"""

from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    working_dir: str
    task_description: str

    branch_name: str
    last_result: str
    artifacts: dict[str, Any]

    error: str | None
