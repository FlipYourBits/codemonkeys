"""High-level Pipeline: build a LangGraph workflow from string step names.

Steps are resolved from the node registry. Lists within `steps` create
parallel fan-out (same semantics as `chain()`).
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Union

from langgraph.graph import StateGraph

from langclaude.graphs import chain
from langclaude.registry import register, resolve

Step = Union[str, tuple[str, str]]


class Pipeline:
    """Build and run a LangGraph workflow from registry node names.

    Args:
        working_dir: repo root passed into state as "working_dir".
        task: task description passed into state as "task_description".
        steps: list of node name strings, (graph_name, registry_key) tuples,
            or nested lists for parallel fan-out.
        extra_skills: skill names injected into every node whose factory
            accepts an `extra_skills` parameter.
        config: per-node overrides keyed by step name or graph_name.
        custom_nodes: dict mapping namespaced names to node callables.
            Registered before resolution. Inline alternative to register().
        verbose: default verbose flag for nodes that accept it.
        extra_state: additional key-value pairs merged into initial state.
    """

    def __init__(
        self,
        *,
        working_dir: str,
        task: str = "",
        steps: Sequence[Any],
        extra_skills: Sequence[str | Path] = (),
        config: dict[str, dict[str, Any]] | None = None,
        custom_nodes: dict[str, Any] | None = None,
        verbose: bool = False,
        extra_state: dict[str, Any] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        self.working_dir = working_dir
        self.task = task
        self.steps = list(steps)
        self.extra_skills = list(extra_skills)
        self.config = dict(config or {})
        self.custom_nodes = dict(custom_nodes or {})
        self.verbose = verbose
        self.extra_state = dict(extra_state or {})

        self._register_custom_nodes()
        self._app = self._build()

    def _register_custom_nodes(self) -> None:
        for key, node in self.custom_nodes.items():
            factory = (lambda _n=node, **kw: _n) if callable(node) else node
            if "/" not in key:
                register(key, factory, namespace="custom")
            else:
                ns, _, name = key.rpartition("/")
                register(name, factory, namespace=ns)

    def _apply_overrides(self, factory: Any, overrides: dict[str, Any]) -> Any:
        sig = inspect.signature(factory)
        params = sig.parameters

        if "extra_skills" in params and self.extra_skills:
            existing = list(overrides.get("extra_skills", ()))
            merged = list(dict.fromkeys([*self.extra_skills, *existing]))
            overrides["extra_skills"] = merged

        if "verbose" in params and "verbose" not in overrides:
            overrides["verbose"] = self.verbose

        if overrides:
            return factory(**overrides)
        return factory()

    @staticmethod
    def _merge_wrap(node: Any) -> Any:
        """Wrap a node callable so it merges incoming state with its output.

        ``StateGraph(dict)`` replaces state with whatever the node returns.
        We want partial-dict semantics: the node returns only new/changed keys
        and everything else is preserved.
        """
        if inspect.iscoroutinefunction(node):

            async def _wrapper(state):
                result = await node(state)
                if isinstance(result, dict):
                    return {**state, **result}
                return result

            return _wrapper

        def _wrapper(state):
            result = node(state)
            if isinstance(result, dict):
                return {**state, **result}
            return result

        return _wrapper

    def _instantiate(self, name: str) -> tuple[str, Any]:
        factory = resolve(name)
        graph_name = name.rsplit("/", 1)[-1]
        overrides = dict(self.config.get(name, {}))
        node = self._apply_overrides(factory, overrides)
        return graph_name, self._merge_wrap(node)

    def _resolve_step(self, step: Any) -> Any:
        if isinstance(step, list):
            return [self._resolve_step(s) for s in step]
        if isinstance(step, tuple):
            graph_name, registry_key = step
            factory = resolve(registry_key)
            overrides = dict(self.config.get(registry_key, {}))
            overrides.update(self.config.get(graph_name, {}))
            node = self._apply_overrides(factory, overrides)
            return graph_name, self._merge_wrap(node)
        return self._instantiate(step)

    def _build(self) -> Any:
        graph = StateGraph(dict)
        resolved = [self._resolve_step(s) for s in self.steps]
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
