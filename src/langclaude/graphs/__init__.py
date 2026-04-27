"""Graph construction utilities."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph


def chain(graph: StateGraph, *steps: Any) -> None:
    """Wire nodes in sequence. Lists create parallel fan-out/fan-in.

    START and END are added automatically — no need to pass them.

    Each step is one of:
        - A (name, callable) tuple: registers the node and wires it.
        - A string: an already-added node name (rare).
        - A list of the above: fan-out from the previous step to all
          items, then fan-in from all items to the next step.
          Items within a list can themselves be lists for sequential
          sub-chains within the parallel group.

    Example::

        chain(graph,
            ("new_branch", claude_new_branch_node()),
            ("implementer", claude_feature_implementer_node()),
            [
                ("code_review", review),
                ("security_audit", security),
                [("test_runner", tests), ("test_coverage", coverage)],
            ],
            ("ruff_final", ruff_fix),
        )

    Produces::

        START → new_branch → implementer → code_review      ─┐
                                          → security_audit    ├→ ruff_final → END
                                          → test_runner → test_coverage ─┘
    """
    all_steps = list(steps)

    if all_steps and all_steps[0] is not START:
        all_steps.insert(0, START)
    if all_steps and all_steps[-1] is not END:
        all_steps.append(END)

    prev: str | list[str] | None = None

    for step in all_steps:
        if isinstance(step, list):
            entry_names: list[str] = []
            exit_names: list[str] = []
            for item in step:
                if isinstance(item, list):
                    sub_names = _register_chain(graph, item)
                    entry_names.append(sub_names[0])
                    exit_names.append(sub_names[-1])
                else:
                    name = _register(graph, item)
                    entry_names.append(name)
                    exit_names.append(name)
            if prev is not None:
                _connect(graph, prev, entry_names)
            prev = exit_names
        else:
            name = _register(graph, step)
            if prev is not None:
                _connect(graph, prev, name)
            prev = name


def _register(graph: StateGraph, step: Any) -> str:
    """Register a step and return its name. Strings pass through."""
    if isinstance(step, tuple):
        name, node = step
        graph.add_node(name, node)
        return name
    return step


def _register_chain(graph: StateGraph, items: list[Any]) -> list[str]:
    """Register a sequential sub-chain, return list of names."""
    names: list[str] = []
    for item in items:
        name = _register(graph, item)
        if names:
            graph.add_edge(names[-1], name)
        names.append(name)
    return names


def _connect(
    graph: StateGraph,
    src: str | list[str],
    dst: str | list[str],
) -> None:
    srcs = src if isinstance(src, list) else [src]
    dsts = dst if isinstance(dst, list) else [dst]
    for s in srcs:
        for d in dsts:
            graph.add_edge(s, d)
