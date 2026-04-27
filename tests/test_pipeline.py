from __future__ import annotations

import asyncio

import pytest

from langclaude.pipeline import Pipeline


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
            config={
                "python_ruff_final": {"name": "python_ruff_final"}
            },
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
