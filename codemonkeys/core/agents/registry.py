"""Agent registry — declares agent capabilities and wires producers to consumers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


class AgentRole(Enum):
    ANALYZER = "analyzer"
    EXECUTOR = "executor"


class AgentSpec(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(description="Unique identifier for this agent")
    role: AgentRole = Field(description="Whether this agent analyzes or executes")
    description: str = Field(description="Human-readable description shown in the TUI")
    scope: Literal["file", "project"] = Field(
        description="Whether this agent operates on a single file or the whole project"
    )
    produces: Any = Field(
        default=None, description="Pydantic model type this agent outputs"
    )
    consumes: Any = Field(
        default=None, description="Pydantic model type this agent accepts as input"
    )
    make: Callable[..., Any] = Field(
        description="Factory function that creates the AgentDefinition"
    )


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.name] = spec

    def get(self, name: str) -> AgentSpec | None:
        return self._agents.get(name)

    def list_by_role(self, role: AgentRole) -> list[AgentSpec]:
        return [s for s in self._agents.values() if s.role == role]

    def compatible_executors(self, analyzer_name: str) -> list[AgentSpec]:
        analyzer = self._agents.get(analyzer_name)
        if not analyzer or not analyzer.produces:
            return []
        executors = self.list_by_role(AgentRole.EXECUTOR)
        compatible = []
        for executor in executors:
            if executor.consumes and _types_compatible(
                analyzer.produces, executor.consumes
            ):
                compatible.append(executor)
        return compatible


def _types_compatible(produces: type, consumes: type) -> bool:
    if produces is consumes:
        return True
    produces_fields = _get_nested_model_types(produces)
    consumes_fields = _get_nested_model_types(consumes)
    return bool(produces_fields & consumes_fields)


def _get_nested_model_types(model: type) -> set[type]:
    types: set[type] = {model}
    if hasattr(model, "model_fields"):
        for field_info in model.model_fields.values():
            annotation = field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                types |= _get_nested_model_types(annotation)
            origin = getattr(annotation, "__origin__", None)
            if origin is list:
                args = getattr(annotation, "__args__", ())
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        types |= _get_nested_model_types(arg)
    return types
