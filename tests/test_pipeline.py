from __future__ import annotations

import asyncio

import pytest

from langclaude.pipeline import Pipeline
from langclaude.nodes.base import Verbosity


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from langclaude import registry as reg

    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


class TestPipelineConstruction:
    def test_creates_with_string_steps(self):
        p = Pipeline(
            working_dir="/tmp/repo",
            task="add healthz",
            steps=["python_lint", "python_format"],
        )
        assert p.working_dir == "/tmp/repo"

    def test_rejects_empty_steps(self):
        with pytest.raises(ValueError, match="steps"):
            Pipeline(working_dir="/tmp", task="x", steps=[])

    def test_unknown_step_raises(self):
        with pytest.raises(KeyError, match="nonexistent"):
            Pipeline(working_dir="/tmp", task="x", steps=["nonexistent"])

    def test_parallel_steps(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[["python_lint", "python_format"]],
        )
        assert p._app is not None

    def test_config_overrides(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint"],
            config={"python_lint": {"fix": False}},
        )
        assert p._app is not None

    def test_aliased_tuple_step(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint", ("python_ruff_final", "python_lint")],
            config={"python_ruff_final": {"name": "python_ruff_final"}},
        )
        assert p._app is not None

    def test_duplicate_step_auto_suffixed(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint", "python_format", "python_lint"],
        )
        assert p._app is not None


class TestPipelineCustomNodes:
    def test_custom_node_inline(self):
        async def my_node(state):
            return {"out": "ok"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/deploy"],
            custom_nodes={"custom/deploy": my_node},
        )
        assert p._app is not None

    def test_run_with_custom_nodes(self):
        calls = []

        async def step_a(state):
            calls.append("a")
            return {"a_out": "done"}

        async def step_b(state):
            calls.append("b")
            return {"b_out": "done"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert calls == ["a", "b"]
        assert final.get("a_out") == "done"


class TestCostTracking:
    def test_node_costs_accumulated(self):
        costs = []

        async def step_a(state):
            costs.append("a")
            return {"a": "done", "last_cost_usd": 0.05}

        async def step_b(state):
            costs.append("b")
            return {"b": "done", "last_cost_usd": 0.10}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["node_costs"] == {"a": 0.05, "b": 0.10}
        assert final["total_cost_usd"] == pytest.approx(0.15)
        assert "last_cost_usd" not in final

    def test_node_costs_zero_for_no_cost_node(self):
        async def step_a(state):
            return {"a": "done"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["node_costs"] == {"a": 0.0}
        assert final["total_cost_usd"] == 0.0


class TestRequiresConfig:
    def test_prior_results_injected(self):
        async def step_a(state):
            return {"a": '{"findings": []}', "last_cost_usd": 0.0}

        async def step_b(state):
            assert "_prior_results" in state
            assert "### a" in state["_prior_results"]
            assert '{"findings": []}' in state["_prior_results"]
            return {"b": "saw context", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
            config={"b": {"requires": ["a"]}},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["b"] == "saw context"

    def test_no_requires_no_prior_results(self):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.0}

        async def step_b(state):
            assert "_prior_results" not in state or state["_prior_results"] == ""
            return {"b": "no context", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["b"] == "no context"

    def test_requires_invalid_node_raises(self):
        async def step_a(state):
            return {"a": "done"}

        with pytest.raises(ValueError, match="requires.*nonexistent"):
            Pipeline(
                working_dir="/tmp",
                task="test",
                steps=["custom/a"],
                custom_nodes={"custom/a": step_a},
                config={"a": {"requires": ["nonexistent"]}},
            )


class TestStatusLine:
    def test_normal_verbosity_prints_status(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.normal,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        err = capsys.readouterr().err
        assert "a" in err
        assert "done" in err

    def test_normal_verbosity_uses_display(self):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.normal,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        assert p._display is not None

    def test_silent_verbosity_no_output(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.silent,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        err = capsys.readouterr().err
        assert err == ""


class TestPublicAPI:
    def test_importable_from_langclaude(self):
        from langclaude import (
            Pipeline,
            register,
            list_builtins,
            list_registered,
            resolve,
        )

        for obj in (Pipeline, register, list_builtins, list_registered, resolve):
            assert obj is not None
