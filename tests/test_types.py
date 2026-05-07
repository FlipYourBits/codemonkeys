from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage


class DummySchema(BaseModel):
    message: str


def test_agent_definition_is_frozen():
    agent = AgentDefinition(
        name="test",
        model="sonnet",
        system_prompt="You are a test agent.",
        tools=["Read", "Grep"],
    )
    assert agent.name == "test"
    assert agent.output_schema is None
    try:
        agent.name = "changed"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_agent_definition_with_schema():
    agent = AgentDefinition(
        name="reviewer",
        model="haiku",
        system_prompt="Review code.",
        tools=["Read"],
        output_schema=DummySchema,
    )
    assert agent.output_schema is DummySchema


def test_token_usage_defaults():
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_run_result_fields():
    usage = TokenUsage(input_tokens=1000, output_tokens=200)
    result = RunResult(
        output=None,
        text="hello",
        usage=usage,
        cost_usd=0.01,
        duration_ms=500,
    )
    assert result.error is None
    assert result.cost_usd == 0.01
