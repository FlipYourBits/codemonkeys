"""Extra Pipeline tests: sync node wrapping, _is_async, model override, extra_state."""

from __future__ import annotations

import asyncio

import pytest

from agentpipe.pipeline import Pipeline


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from agentpipe import registry as reg

    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


class TestIsAsync:
    def test_async_function(self):
        async def f(state):
            return {}

        assert Pipeline._is_async(f) is True

    def test_sync_function(self):
        def f(state):
            return {}

        assert Pipeline._is_async(f) is False

    def test_async_callable_object(self):
        class Node:
            async def __call__(self, state):
                return {}

        assert Pipeline._is_async(Node()) is True

    def test_sync_callable_object(self):
        class Node:
            def __call__(self, state):
                return {}

        assert Pipeline._is_async(Node()) is False


class TestRunNode:
    def _make_pipeline(self):
        async def _dummy(state):
            return {}

        return Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/dummy"],
            custom_nodes={"custom/dummy": _dummy},
        )

    def test_sync_node_returns_dict(self):
        def node(state):
            return {"out": "val"}

        p = self._make_pipeline()
        result = asyncio.run(p._run_node("out", node, {"existing": 1}))
        assert result["out"] == "val"

    def test_async_node_returns_dict(self):
        async def node(state):
            return {"out": "val"}

        p = self._make_pipeline()
        result = asyncio.run(p._run_node("out", node, {"existing": 1}))
        assert result["out"] == "val"

    def test_sync_non_dict_returns_empty(self):
        def node(state):
            return "not a dict"

        p = self._make_pipeline()
        result = asyncio.run(p._run_node("node", node, {"existing": 1}))
        assert result == {}

    def test_async_non_dict_returns_empty(self):
        async def node(state):
            return "not a dict"

        p = self._make_pipeline()
        result = asyncio.run(p._run_node("node", node, {"existing": 1}))
        assert result == {}


class TestDedupName:
    def test_first_occurrence(self):
        p = Pipeline.__new__(Pipeline)
        seen = {}
        assert p._dedup_name("lint", seen) == "lint"

    def test_second_occurrence(self):
        p = Pipeline.__new__(Pipeline)
        seen = {"lint": 1}
        assert p._dedup_name("lint", seen) == "lint_2"


class TestPipelineWithModel:
    def test_model_set(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_test"],
            model="opus",
        )
        assert p.model == "opus"


class TestPipelineSyncCustomNode:
    def test_sync_custom_node_runs(self):
        def sync_node(state):
            return {"sync_out": "ok"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/sync"],
            custom_nodes={"custom/sync": sync_node},
        )
        final = asyncio.run(p.run())
        assert final.get("sync_out") == "ok"

    def test_extra_state_passed(self):
        captures = {}

        async def capture_node(state):
            captures.update(state)
            return {"done": True}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/cap"],
            custom_nodes={"custom/cap": capture_node},
            extra_state={"base_ref": "develop"},
        )
        asyncio.run(p.run())
        assert captures["base_ref"] == "develop"

    def test_run_with_extra_kwargs(self):
        captures = {}

        async def capture_node(state):
            captures.update(state)
            return {"done": True}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/cap"],
            custom_nodes={"custom/cap": capture_node},
        )
        asyncio.run(p.run(custom_key="custom_val"))
        assert captures["custom_key"] == "custom_val"


class TestPipelineCustomNodeNamespace:
    def test_bare_key_uses_custom_namespace(self):
        async def my_node(state):
            return {"out": "ok"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/bare_node"],
            custom_nodes={"bare_node": my_node},
        )
        assert len(p._ordered_names) > 0
