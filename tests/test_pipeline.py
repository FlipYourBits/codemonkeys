from __future__ import annotations

import asyncio

import pytest

from agentpipe.pipeline import Pipeline
from agentpipe.nodes.base import Verbosity
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_format import PythonFormat


class TestPipelineConstruction:
    def test_creates_with_node_steps(self):
        p = Pipeline(
            working_dir="/tmp/repo",
            task="add healthz",
            steps=[PythonLint(), PythonFormat()],
        )
        assert p.working_dir == "/tmp/repo"

    def test_rejects_empty_steps(self):
        with pytest.raises(ValueError, match="steps"):
            Pipeline(working_dir="/tmp", task="x", steps=[])

    def test_parallel_steps(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[[PythonLint(), PythonFormat()]],
        )
        assert len(p._ordered_names) > 0

    def test_aliased_tuple_step(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[PythonLint(), ("ruff_final", PythonLint())],
        )
        assert "ruff_final" in p._ordered_names

    def test_duplicate_step_auto_suffixed(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[PythonLint(), PythonFormat(), PythonLint()],
        )
        assert "python_lint" in p._ordered_names
        assert "python_lint_2" in p._ordered_names


class TestPipelineCustomCallables:
    def test_bare_callable_runs(self):
        async def my_node(state):
            return {"out": "ok"}

        my_node.__name__ = "deploy"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[my_node],
        )
        assert "deploy" in p._ordered_names

    def test_run_with_callables(self):
        calls = []

        async def step_a(state):
            calls.append("a")
            return {"a_out": "done"}

        async def step_b(state):
            calls.append("b")
            return {"b_out": "done"}

        step_a.__name__ = "a"
        step_b.__name__ = "b"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a, step_b],
        )
        final = asyncio.run(p.run())
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

        step_a.__name__ = "a"
        step_b.__name__ = "b"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a, step_b],
        )
        final = asyncio.run(p.run())
        assert final["node_costs"] == {"a": 0.05, "b": 0.10}
        assert final["total_cost_usd"] == pytest.approx(0.15)
        assert "last_cost_usd" not in final

    def test_node_costs_zero_for_no_cost_node(self):
        async def step_a(state):
            return {"a": "done"}

        step_a.__name__ = "a"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a],
        )
        final = asyncio.run(p.run())
        assert final["node_costs"] == {"a": 0.0}
        assert final["total_cost_usd"] == 0.0


class TestStatusLine:
    def test_normal_verbosity_prints_status(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        step_a.__name__ = "a"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a],
            verbosity=Verbosity.normal,
        )
        asyncio.run(p.run())
        err = capsys.readouterr().err
        assert "a" in err
        assert "done" in err

    def test_normal_verbosity_uses_display(self):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        step_a.__name__ = "a"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a],
            verbosity=Verbosity.normal,
        )
        asyncio.run(p.run())
        assert p._display is not None

    def test_silent_verbosity_no_output(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.0}

        step_a.__name__ = "a"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a],
            verbosity=Verbosity.silent,
        )
        asyncio.run(p.run())
        err = capsys.readouterr().err
        assert err == ""


class TestLogDir:
    def test_log_dir_creates_per_node_files(self, tmp_path):
        async def step_a(state):
            return {"a": "hello from a", "last_cost_usd": 0.0}

        async def step_b(state):
            return {"b": "hello from b", "last_cost_usd": 0.0}

        step_a.__name__ = "a"
        step_b.__name__ = "b"
        log_dir = tmp_path / "logs"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a, step_b],
            log_dir=log_dir,
        )
        asyncio.run(p.run())
        assert (log_dir / "a.log").exists()
        assert (log_dir / "b.log").exists()

    def test_log_dir_with_verbosity_writes_files(self, tmp_path):
        from agentpipe.nodes.base import ShellNode

        log_dir = tmp_path / "logs"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[ShellNode(name="echo_node", command="echo hello")],
            verbosity=Verbosity.normal,
            log_dir=log_dir,
        )
        asyncio.run(p.run())
        log_file = log_dir / "echo_node.log"
        assert log_file.exists()
        assert log_file.read_text().strip() != ""

    def test_no_log_dir_no_files(self, tmp_path):
        async def step_a(state):
            return {"a": "done"}

        step_a.__name__ = "a"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[step_a],
        )
        asyncio.run(p.run())
        assert not (tmp_path / "a.log").exists()


class TestPublicAPI:
    def test_importable_from_agentpipe(self):
        from agentpipe import (
            Display,
            Pipeline,
        )

        for obj in (Display, Pipeline):
            assert obj is not None
