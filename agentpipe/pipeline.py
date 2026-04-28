"""High-level Pipeline: build and run a workflow from node instances.

Steps are node instances (or bare callables). Lists within ``steps``
create parallel fan-out via ``asyncio.gather``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentpipe.display import Display
from agentpipe.nodes.base import Verbosity, _node_name


class Pipeline:
    """Build and run a workflow from node instances.

    Args:
        working_dir: repo root passed into state as "working_dir".
        task: task description passed into state as "task_description".
        steps: list of node instances, (alias, node) tuples for name
            overrides, or nested lists for parallel fan-out. Duplicate
            names are auto-suffixed (e.g. "python_lint", "python_lint_2").
        verbosity: default verbosity for nodes that accept it.
        extra_state: additional key-value pairs merged into initial state.
    """

    def __init__(
        self,
        *,
        working_dir: str,
        task: str = "",
        steps: Sequence[Any],
        verbosity: Verbosity = Verbosity.silent,
        extra_state: dict[str, Any] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        self.working_dir = working_dir
        self.task = task
        self.steps = list(steps)
        self.verbosity = verbosity
        self.extra_state = dict(extra_state or {})
        self._display: Display | None = None

        self._node_costs: dict[str, float] = {}
        self._node_outputs: dict[str, str] = {}
        self._resolved: list[Any] = self._build()
        self._ordered_names = self._flatten_names(self._resolved)

    @staticmethod
    def _is_async(node: Any) -> bool:
        if inspect.iscoroutinefunction(node):
            return True
        call = getattr(node, "__call__", None)
        return call is not None and inspect.iscoroutinefunction(call)

    def _node_enter(
        self, graph_name: str, node: Any, state: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        t0 = 0.0
        if self._display is not None:
            self._display.node_start(graph_name)
            t0 = time.time()
            if hasattr(node, "on_message") and self.verbosity in (
                Verbosity.normal,
                Verbosity.verbose,
            ):
                from agentpipe.nodes.base import _make_printer

                node.on_message = _make_printer(self.verbosity, display=self._display)
            if hasattr(node, "on_output") and self.verbosity in (
                Verbosity.normal,
                Verbosity.verbose,
            ):
                node.on_output = lambda name, line: self._display.node_output(
                    name, line
                )
            if hasattr(node, "on_warn"):
                from agentpipe.budget import default_on_warn

                node.on_warn = lambda cost, cap: default_on_warn(
                    cost, cap, display=self._display
                )
            if hasattr(node, "prompt_fn"):
                node.prompt_fn = self._display.prompt
        return state, t0

    def _node_exit(self, graph_name: str, result: Any, t0: float) -> dict[str, Any]:
        if not isinstance(result, dict):
            if self._display is not None:
                self._display.node_done(graph_name, elapsed=time.time() - t0)
            return {}

        cost = result.pop("last_cost_usd", 0.0)
        self._node_costs[graph_name] = cost
        if self._display is not None:
            self._display.node_done(graph_name, elapsed=time.time() - t0, cost=cost)

        if graph_name in result:
            self._node_outputs[graph_name] = result[graph_name]
        return result

    async def _run_node(
        self, graph_name: str, node: Any, state: dict[str, Any]
    ) -> dict[str, Any]:
        state, t0 = self._node_enter(graph_name, node, state)
        if Pipeline._is_async(node):
            result = await node(state)
        else:
            result = await asyncio.to_thread(node, state)
        return self._node_exit(graph_name, result, t0)

    def _dedup_name(self, name: str, seen: dict[str, int]) -> str:
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 1:
            return name
        return f"{name}_{seen[name]}"

    def _resolve_step(self, step: Any, seen: dict[str, int]) -> Any:
        if isinstance(step, list):
            return [self._resolve_step(s, seen) for s in step]
        if isinstance(step, tuple):
            alias, node = step
            seen[alias] = seen.get(alias, 0) + 1
            return alias, node
        name = _node_name(step)
        graph_name = self._dedup_name(name, seen)
        return graph_name, step

    @staticmethod
    def _flatten_names(resolved: list[Any]) -> list[str]:
        names: list[str] = []
        for item in resolved:
            if isinstance(item, list):
                for sub in item:
                    names.append(sub[0])
            else:
                names.append(item[0])
        return names

    @staticmethod
    def _validate_reads_from(resolved: list[Any]) -> None:
        """Raise if any node reads from a key not produced by an earlier step."""
        available: set[str] = set()
        for step in resolved:
            pairs = step if isinstance(step, list) else [step]
            for graph_name, node in pairs:
                deps = getattr(node, "_reads_from_keys", None) or []
                missing = [k for k in deps if k not in available]
                if missing:
                    raise ValueError(
                        f"node {graph_name!r} reads_from {missing} "
                        f"but those nodes are not in earlier steps"
                    )
            for graph_name, _ in pairs:
                available.add(graph_name)

    def _build(self) -> list[Any]:
        seen: dict[str, int] = {}
        resolved = [self._resolve_step(s, seen) for s in self.steps]
        self._validate_reads_from(resolved)
        return resolved

    async def _run_steps(self, state: dict[str, Any]) -> dict[str, Any]:
        for step in self._resolved:
            if isinstance(step, list):
                results = await asyncio.gather(
                    *[self._run_node(name, node, dict(state)) for name, node in step]
                )
                for result in results:
                    state.update(result)
            else:
                name, node = step
                result = await self._run_node(name, node, state)
                state.update(result)
        return state

    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )
        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        try:
            result = await self._run_steps(state)
            result["node_costs"] = dict(self._node_costs)
            result["total_cost_usd"] = sum(self._node_costs.values())
            result["node_outputs"] = dict(self._node_outputs)
            self._save_run(result)
            return result
        finally:
            if self._display is not None:
                self._display.stop()

    def _save_run(self, result: dict[str, Any]) -> Path | None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        runs_dir = Path(self.working_dir) / ".agentpipe" / "runs"
        try:
            runs_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        steps_summary = []
        for name in self._ordered_names:
            steps_summary.append(
                {
                    "node": name,
                    "cost_usd": self._node_costs.get(name, 0.0),
                    "output": self._node_outputs.get(name, ""),
                }
            )
        run_data = {
            "timestamp": ts,
            "working_dir": self.working_dir,
            "task": self.task,
            "steps": list(self._ordered_names),
            "total_cost_usd": sum(self._node_costs.values()),
            "node_summary": steps_summary,
        }
        path = runs_dir / f"{ts}.json"
        path.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
        return path

    def print_results(self) -> None:
        """Print a per-node cost summary table. Call after ``run()``."""
        display = self._display or Display(steps=[], title="Results", live=False)
        display.print_results(self._node_costs, self._node_outputs)
