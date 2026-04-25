"""End-to-end example: name a branch, check it out, implement a feature.

Run with:

    python -m langclaude.graphs.example /path/to/repo "Add a /healthz endpoint"
"""

from __future__ import annotations

import asyncio
import sys

from langgraph.graph import END, START, StateGraph

from langclaude.nodes.base import ShellNode
from langclaude.nodes.branch_namer import branch_namer_node
from langclaude.nodes.feature_implementer import feature_implementer_node
from langclaude.permissions import ask_via_stdin
from langclaude.state import WorkflowState


def build_graph():
    name_branch = branch_namer_node(on_unmatched=ask_via_stdin)

    checkout = ShellNode(
        name="git_checkout",
        command=lambda s: ["git", "checkout", "-b", s["branch_name"].strip()],
    )

    implement = feature_implementer_node(on_unmatched=ask_via_stdin)

    graph = StateGraph(WorkflowState)
    graph.add_node("name_branch", name_branch)
    graph.add_node("checkout", checkout)
    graph.add_node("implement", implement)

    graph.add_edge(START, "name_branch")
    graph.add_edge("name_branch", "checkout")
    graph.add_edge("checkout", "implement")
    graph.add_edge("implement", END)

    return graph.compile()


async def main(working_dir: str, task: str) -> None:
    graph = build_graph()
    initial: WorkflowState = {
        "working_dir": working_dir,
        "task_description": task,
    }
    final = await graph.ainvoke(initial)
    print("\n=== Final state ===")
    for key, value in final.items():
        print(f"{key}: {value!r}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m langclaude.graphs.example <working_dir> <task>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
