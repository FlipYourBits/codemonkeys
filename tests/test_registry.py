from __future__ import annotations

from pydantic import BaseModel, Field

from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
from codemonkeys.core.agents.registry import AgentRegistry, AgentRole, AgentSpec


class _MockOutput(BaseModel):
    result: str = Field(description="test")


class _MockInput(BaseModel):
    data: str = Field(description="test")


class TestAgentRegistry:
    def test_register_and_list(self) -> None:
        registry = AgentRegistry()
        spec = AgentSpec(
            name="test-analyzer",
            role=AgentRole.ANALYZER,
            description="Test agent",
            scope="file",
            produces=_MockOutput,
            consumes=None,
            make=lambda: None,
        )
        registry.register(spec)
        assert registry.get("test-analyzer") == spec

    def test_list_by_role(self) -> None:
        registry = AgentRegistry()
        analyzer = AgentSpec(
            name="analyzer",
            role=AgentRole.ANALYZER,
            description="Analyzer",
            scope="file",
            produces=_MockOutput,
            consumes=None,
            make=lambda: None,
        )
        executor = AgentSpec(
            name="executor",
            role=AgentRole.EXECUTOR,
            description="Executor",
            scope="file",
            produces=None,
            consumes=_MockInput,
            make=lambda: None,
        )
        registry.register(analyzer)
        registry.register(executor)
        analyzers = registry.list_by_role(AgentRole.ANALYZER)
        assert len(analyzers) == 1
        assert analyzers[0].name == "analyzer"

    def test_compatible_executors(self) -> None:
        registry = AgentRegistry()
        analyzer = AgentSpec(
            name="reviewer",
            role=AgentRole.ANALYZER,
            description="File reviewer",
            scope="file",
            produces=FileFindings,
            consumes=None,
            make=lambda: None,
        )
        fixer = AgentSpec(
            name="fixer",
            role=AgentRole.EXECUTOR,
            description="Code fixer",
            scope="file",
            produces=None,
            consumes=FixRequest,
            make=lambda: None,
        )
        unrelated = AgentSpec(
            name="unrelated",
            role=AgentRole.EXECUTOR,
            description="Unrelated",
            scope="file",
            produces=None,
            consumes=_MockInput,
            make=lambda: None,
        )
        registry.register(analyzer)
        registry.register(fixer)
        registry.register(unrelated)
        executors = registry.compatible_executors("reviewer")
        assert any(e.name == "fixer" for e in executors)

    def test_get_nonexistent_returns_none(self) -> None:
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None
