"""High-level Pipeline: build a LangGraph workflow from string step names.

Steps are resolved from the node registry. Lists within `steps` create
parallel fan-out (same semantics as `chain()`).
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Sequence
from typing import Any, Union

from langgraph.graph import StateGraph

from langclaude.display import Display
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
        self._display: Display | None = None

        self._requires_map: dict[str, list[str]] = {}
        self._register_custom_nodes()
        self._ordered_names = self._compute_ordered_names()
        self._app: Any | None = None

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

    def _compute_ordered_names(self) -> list[str]:
        seen: dict[str, int] = {}
        resolved = [self._resolve_step_for_names(s, seen) for s in self.steps]
        return self._flatten_names(resolved)

    def _resolve_step_for_names(self, step: Any, seen: dict[str, int]) -> Any:
        if isinstance(step, list):
            return [self._resolve_step_for_names(s, seen) for s in step]
        if isinstance(step, tuple):
            graph_name = step[0]
            seen[graph_name] = seen.get(graph_name, 0) + 1
            return (graph_name, None)
        base = step.rsplit("/", 1)[-1]
        graph_name = self._dedup_name(base, seen)
        return (graph_name, None)

    def _apply_overrides(self, factory: Any, overrides: dict[str, Any]) -> Any:
        sig = inspect.signature(factory)
        params = sig.parameters

        if "verbosity" in params and "verbosity" not in overrides:
            if self.verbosity == Verbosity.normal:
                overrides["verbosity"] = Verbosity.silent
            else:
                overrides["verbosity"] = self.verbosity

        if self.model and "model" in params and "model" not in overrides:
            overrides["model"] = self.model

        if "prompt_fn" in params and "prompt_fn" not in overrides:
            if self._display is not None:
                overrides["prompt_fn"] = self._display.prompt

        if overrides:
            return factory(**overrides)
        return factory()

    @staticmethod
    def _is_async(node: Any) -> bool:
        if inspect.iscoroutinefunction(node):
            return True
        call = getattr(node, "__call__", None)
        return call is not None and inspect.iscoroutinefunction(call)

    def _inject_prior_results(self, state: dict[str, Any], graph_name: str) -> dict[str, Any]:
        requires = self._requires_map.get(graph_name, [])
        if not requires:
            return state
        node_outputs = state.get("node_outputs", {})
        parts = ["## Prior results\n"]
        for req in requires:
            output = node_outputs.get(req, "")
            parts.append(f"### {req}\n{output}\n")
        return {**state, "_prior_results": "\n".join(parts)}

    def _node_enter(self, graph_name: str, node: Any, state: dict[str, Any]) -> tuple[dict[str, Any], float]:
        state = self._inject_prior_results(state, graph_name)
        t0 = 0.0
        if self._display is not None:
            self._display.node_start(graph_name)
            t0 = time.time()
            if hasattr(node, 'on_message') and self.verbosity == Verbosity.verbose:
                from langclaude.nodes.base import _make_printer
                node.on_message = _make_printer(self.verbosity, display=self._display)
            if hasattr(node, 'on_warn'):
                from langclaude.budget import default_on_warn
                node.on_warn = lambda cost, cap: default_on_warn(cost, cap, display=self._display)
        return state, t0

    def _node_exit(self, graph_name: str, result: Any, state: dict[str, Any], t0: float) -> Any:
        if not isinstance(result, dict):
            if self._display is not None:
                self._display.node_done(graph_name, elapsed=time.time() - t0)
            return result

        cost = result.pop("last_cost_usd", 0.0)
        if self._display is not None:
            self._display.node_done(graph_name, elapsed=time.time() - t0, cost=cost)

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

    def _make_tracking_wrap(self, graph_name: str, node: Any) -> Any:
        if Pipeline._is_async(node):

            async def _wrapper(state):
                state, t0 = self._node_enter(graph_name, node, state)
                result = await node(state)
                return self._node_exit(graph_name, result, state, t0)

            return _wrapper

        def _wrapper(state):
            state, t0 = self._node_enter(graph_name, node, state)
            result = node(state)
            return self._node_exit(graph_name, result, state, t0)

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
        overrides.pop("requires", None)
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
            overrides.pop("requires", None)
            node = self._apply_overrides(factory, overrides)
            return graph_name, self._make_tracking_wrap(graph_name, node)
        return self._instantiate(step, seen)

    def _validate_requires(self, ordered_names: list[str]) -> None:
        for name in ordered_names:
            node_config = self.config.get(name, {})
            requires = node_config.get("requires", [])
            if not requires:
                continue
            for req in requires:
                if req not in ordered_names or ordered_names.index(req) >= ordered_names.index(name):
                    raise ValueError(
                        f"requires: node {name!r} requires {req!r} but it "
                        f"does not appear earlier in the step list"
                    )
            self._requires_map[name] = requires

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

    def _build(self) -> Any:
        graph = StateGraph(dict)
        seen: dict[str, int] = {}
        resolved = [self._resolve_step(s, seen) for s in self.steps]
        ordered_names = self._flatten_names(resolved)
        self._validate_requires(ordered_names)
        chain(graph, *resolved)
        return graph.compile()

    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )
        if self._app is None:
            self._app = self._build()
        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        try:
            return await self._app.ainvoke(state)
        finally:
            if self._display is not None:
                self._display.stop()
