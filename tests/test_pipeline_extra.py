"""Extra Pipeline tests: sync node wrapping, _is_async, model override, extra_state."""

from __future__ import annotations

import asyncio


from agentpipe.pipeline import Pipeline


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

        _dummy.__name__ = "dummy"
        return Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[_dummy],
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


class TestPipelineSyncCustomNode:
    def test_sync_custom_node_runs(self):
        def sync_node(state):
            return {"sync_out": "ok"}

        sync_node.__name__ = "sync"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[sync_node],
        )
        final = asyncio.run(p.run())
        assert final.get("sync_out") == "ok"

    def test_extra_state_passed(self):
        captures = {}

        async def capture_node(state):
            captures.update(state)
            return {"done": True}

        capture_node.__name__ = "cap"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[capture_node],
            extra_state={"base_ref": "develop"},
        )
        asyncio.run(p.run())
        assert captures["base_ref"] == "develop"

    def test_run_with_extra_kwargs(self):
        captures = {}

        async def capture_node(state):
            captures.update(state)
            return {"done": True}

        capture_node.__name__ = "cap"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[capture_node],
        )
        asyncio.run(p.run(custom_key="custom_val"))
        assert captures["custom_key"] == "custom_val"
