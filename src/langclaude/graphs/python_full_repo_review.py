"""Full Python repository review workflow.

Runs linting, tests, and all review nodes against the entire repo.
No branch creation, no implementation, no committing — pure analysis.

Run with:

    python -m langclaude.graphs.python_full_repo_review /path/to/repo
"""

from __future__ import annotations

import asyncio
import sys

from langgraph.graph import StateGraph

from langclaude.graphs import chain
from langclaude.nodes.code_review import claude_code_review_node
from langclaude.nodes.dependency_audit import claude_dependency_audit_node
from langclaude.nodes.docs_review import claude_docs_review_node
from langclaude.nodes.ruff_node import shell_ruff_fix_node
from langclaude.nodes.security_audit import claude_security_audit_node
from langclaude.nodes.test_coverage import claude_coverage_node
from langclaude.nodes.test_runner import claude_pytest_node


def build_graph(*, verbose: bool = True):
    graph = StateGraph(dict)

    chain(graph,
        [
            ("ruff", shell_ruff_fix_node(name="ruff", fix=False, fail_on_findings=False)),
            [("test_runner", claude_pytest_node()), ("test_coverage", claude_coverage_node(mode="full"))],
            ("code_review", claude_code_review_node(mode="full", verbose=verbose)),
            ("security_audit", claude_security_audit_node(mode="full", verbose=verbose)),
            ("docs_review", claude_docs_review_node(mode="full", verbose=verbose)),
            ("dep_audit", claude_dependency_audit_node()),
        ],
    )

    return graph.compile()


async def main(working_dir: str) -> None:
    graph = build_graph()

    final = await graph.ainvoke({"working_dir": working_dir})

    print("\n=== Full Repo Review ===")
    print(f"tests:      {final.get('test_summary', {})}")
    print(f"coverage:   {final.get('coverage_summary', {})}")
    print(f"dep vulns:  {len(final.get('dep_findings', []))}")
    print(f"review:     {final.get('review_findings', '<none>')[:200]}")
    print(f"security:   {final.get('security_findings', '<none>')[:200]}")
    print(f"docs:       {final.get('docs_findings', '<none>')[:200]}")
    print(f"cost:       ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python -m langclaude.graphs.python_full_repo_review <working_dir>",
            file=sys.stderr,
        )
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
