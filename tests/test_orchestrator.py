import asyncio

import pytest
from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage
from codemonkeys.dashboard.orchestrator import Orchestrator


class _DummyOutput(BaseModel):
    message: str


def _make_agent(name: str = "test_agent") -> AgentDefinition:
    return AgentDefinition(
        name=name,
        model="sonnet",
        system_prompt="You are a test agent.",
        tools=["Read"],
    )


@pytest.fixture
def orchestrator():
    return Orchestrator(max_concurrent=2)


async def test_submit_returns_run_id(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    run_id = await orchestrator.submit(_make_agent(), "test prompt")
    assert run_id.startswith("run_")


async def test_get_run_returns_state(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    run_id = await orchestrator.submit(_make_agent(), "test prompt")
    await asyncio.sleep(0.1)
    state = orchestrator.get_run(run_id)
    assert state is not None
    assert state["status"] in ("running", "completed")


async def test_list_runs(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    await orchestrator.submit(_make_agent("a"), "prompt")
    await orchestrator.submit(_make_agent("b"), "prompt")
    runs = orchestrator.list_runs()
    assert len(runs) == 2


async def test_max_concurrent_queues_excess(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner

    id1 = await orchestrator.submit(_make_agent("a"), "prompt")
    id2 = await orchestrator.submit(_make_agent("b"), "prompt")
    id3 = await orchestrator.submit(_make_agent("c"), "prompt")

    await asyncio.sleep(0.05)

    states = {rid: orchestrator.get_run(rid)["status"] for rid in [id1, id2, id3]}
    assert states[id3] == "queued"
    assert list(states.values()).count("running") == 2

    gate.set()
    await asyncio.sleep(0.1)

    assert orchestrator.get_run(id3)["status"] == "completed"


async def test_cancel_running(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner
    run_id = await orchestrator.submit(_make_agent(), "prompt")
    await asyncio.sleep(0.05)

    cancelled = orchestrator.cancel(run_id)
    assert cancelled is True
    assert orchestrator.get_run(run_id)["status"] == "cancelled"
    gate.set()


async def test_kill_all(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None,
            text="done",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            duration_ms=100,
            agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner
    await orchestrator.submit(_make_agent("a"), "prompt")
    await orchestrator.submit(_make_agent("b"), "prompt")
    await orchestrator.submit(_make_agent("c"), "prompt")
    await asyncio.sleep(0.05)

    orchestrator.kill_all()
    await asyncio.sleep(0.05)

    for run in orchestrator.list_runs():
        assert run["status"] in ("cancelled",)
    gate.set()
