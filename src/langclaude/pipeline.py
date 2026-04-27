"""High-level Pipeline: build a LangGraph workflow from string step names.

Steps are resolved from the node registry. Lists within `steps` create
parallel fan-out (same semantics as `chain()`).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, Union

from langgraph.graph import StateGraph

from langclaude.graphs import chain
from langclaude.nodes.base import Verbosity
from langclaude.registry import register, resolve

Step = Union[str, tuple[str, str]]


class Pipeline:
    """Build and run a LangGraph workflow from registry node names.

    Args:
        working_dir: repo root passed into state as "working_dir".
        task: task description passed into state as "task_description".
        steps: list of node name strings, (graph_name, registry_key) tuples,
            or nested lists for parallel fan-out. Duplicate strings are
            auto-suffixed (e.g. "python_lint", "python_lint_2").
        config: per-node overrides keyed by step name or graph_name.
        custom_nodes: dict mapping namespaced names to node callables.
            Registered before resolution. Inline alternative to register().
        verbosity: default verbosity for nodes that accept it. Per-node
            config overrides this.
        extra_state: additional key-value pairs merged into initial state.
    """

    def __init__(
        self,
        *,
        working_dir: str,
        task: str = "",
        steps: Sequence[Any],
        model: str | None = None,
        config: dict[str, dict[str, Any]] | None = None,
        custom_nodes: dict[str, Any] | None = None,
        verbosity: Verbosity = Verbosity.silent,
        extra_state: dict[str, Any] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        self.working_dir = working_dir
        self.task = task
        self.steps = list(steps)
        self.model = model
        self.config = dict(config or {})
        self.custom_nodes = dict(custom_nodes or {})
        self.verbosity = verbosity
        self.extra_state = dict(extra_state or {})

        self._register_custom_nodes()
        self._app = self._build()

    @staticmethod
    def _wrap_as_factory(node: Any) -> Callable[..., Any]:
        def factory(**kw: Any) -> Any:
            return node

        return factory

    def _register_custom_nodes(self) -> None:
        for key, node in self.custom_nodes.items():
            factory = self._wrap_as_factory(node)
            if "/" not in key:
                register(key, factory, namespace="custom")
            else:
                ns, _, name = key.rpartition("/")
                register(name, factory, namespace=ns)

    def _apply_overrides(self, factory: Any, overrides: dict[str, Any]) -> Any:
        sig = inspect.signature(factory)
        params = sig.parameters

        if "verbosity" in params and "verbosity" not in overrides:
            overrides["verbosity"] = self.verbosity

        if self.model and "model" in params and "model" not in overrides:
            overrides["model"] = self.model

        if overrides:
            return factory(**overrides)
        return factory()

    @staticmethod
    def _is_async(node: Any) -> bool:
        if inspect.iscoroutinefunction(node):
            return True
        call = getattr(node, "__call__", None)
        return call is not None and inspect.iscoroutinefunction(call)

    def _make_tracking_wrap(self, graph_name: str, node: Any) -> Any:
        if Pipeline._is_async(node):

            async def _wrapper(state):
                result = await node(state)
                if not isinstance(result, dict):
                    return result
                cost = result.pop("last_cost_usd", 0.0)
                node_costs = {**state.get("node_costs", {}), graph_name: cost}
                total_cost = state.get("total_cost_usd", 0.0) + cost
                node_outputs = {**state.get("node_outputs", {})}
                if graph_name in result:
                    node_outputs[graph_name] = result[graph_name]
                return {
                    **state,
                    **result,
                    "node_costs": node_costs,
                    "total_cost_usd": total_cost,
                    "node_outputs": node_outputs,
                }

            return _wrapper

        def _wrapper(state):
            result = node(state)
            if not isinstance(result, dict):
                return result
            cost = result.pop("last_cost_usd", 0.0)
            node_costs = {**state.get("node_costs", {}), graph_name: cost}
            total_cost = state.get("total_cost_usd", 0.0) + cost
            node_outputs = {**state.get("node_outputs", {})}
            if graph_name in result:
                node_outputs[graph_name] = result[graph_name]
            return {
                **state,
                **result,
                "node_costs": node_costs,
                "total_cost_usd": total_cost,
                "node_outputs": node_outputs,
            }

        return _wrapper

    def _dedup_name(self, name: str, seen: dict[str, int]) -> str:
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 1:
            return name
        return f"{name}_{seen[name]}"

    def _instantiate(self, name: str, seen: dict[str, int]) -> tuple[str, Any]:
        factory = resolve(name)
        base_name = name.rsplit("/", 1)[-1]
        graph_name = self._dedup_name(base_name, seen)
        overrides = dict(self.config.get(name, {}))
        overrides.update(self.config.get(graph_name, {}))
        if graph_name != base_name:
            overrides.setdefault("name", graph_name)
        node = self._apply_overrides(factory, overrides)
        return graph_name, self._make_tracking_wrap(graph_name, node)

    def _resolve_step(self, step: Any, seen: dict[str, int]) -> Any:
        if isinstance(step, list):
            return [self._resolve_step(s, seen) for s in step]
        if isinstance(step, tuple):
            graph_name, registry_key = step
            seen[graph_name] = seen.get(graph_name, 0) + 1
            factory = resolve(registry_key)
            overrides = dict(self.config.get(registry_key, {}))
            overrides.update(self.config.get(graph_name, {}))
            node = self._apply_overrides(factory, overrides)
            return graph_name, self._make_tracking_wrap(graph_name, node)
        return self._instantiate(step, seen)

    def _build(self) -> Any:
        graph = StateGraph(dict)
        seen: dict[str, int] = {}
        resolved = [self._resolve_step(s, seen) for s in self.steps]
        chain(graph, *resolved)
        return graph.compile()

    async def run(self, **extra: Any) -> dict[str, Any]:
        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        return await self._app.ainvoke(state)
