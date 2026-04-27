"""Python feature implementation workflow.

End-to-end graph: takes a task description, creates a branch, implements
the feature, runs linting/tests/reviews, fixes issues, and commits.

Run with:

    python -m langclaude.graphs.python_new_feature /path/to/repo "add a retry decorator"
"""

from __future__ import annotations

import asyncio
import shlex
import sys

from langgraph.graph import StateGraph

from langclaude.graphs import chain
from langclaude.nodes.base import ShellNode
from langclaude.nodes.branch_namer import claude_new_branch_node
from langclaude.nodes.code_review import claude_code_review_node
from langclaude.nodes.dependency_audit import claude_dependency_audit_node
from langclaude.nodes.docs_review import claude_docs_review_node
from langclaude.nodes.feature_implementer import claude_feature_implementer_node
from langclaude.nodes.ruff_node import shell_ruff_fix_node, shell_ruff_fmt_node
from langclaude.nodes.security_audit import claude_security_audit_node
from langclaude.nodes.test_coverage import claude_coverage_node
from langclaude.nodes.test_runner import claude_pytest_node


def build_graph(*, base_ref: str = "main", verbose: bool = True):
    graph = StateGraph(dict)

    chain(graph,
        ("new_branch", claude_new_branch_node()),
        ("implementer", claude_feature_implementer_node(extra_skills=["python-clean-code"], verbose=verbose)),
        ("ruff_fix", shell_ruff_fix_node()),
        ("ruff_fmt", shell_ruff_fmt_node()),
        ("test_runner", claude_pytest_node()),
        ("test_coverage", claude_coverage_node(mode="diff", base_ref_key="base_ref")),
        [
            ("code_review", claude_code_review_node(mode="diff", verbose=verbose)),
            ("security_audit", claude_security_audit_node(mode="diff", verbose=verbose)),
            ("docs_review", claude_docs_review_node(mode="diff", verbose=verbose)),
            ("dep_audit", claude_dependency_audit_node()),
        ],
        ("ruff_final", shell_ruff_fix_node(name="ruff_final", output_key="ruff_final_output")),
        ("commit", ShellNode(
            name="commit",
            command=lambda s: [
                "bash", "-c",
                "git add -A && git commit -m "
                + shlex.quote(f"feat: {s.get('task_description', 'implement feature')}")
            ],
            output_key="last_result",
            check=True,
        )),
    )

    return graph.compile()


async def main(working_dir: str, task: str, base_ref: str = "main") -> None:
    graph = build_graph(base_ref=base_ref)

    final = await graph.ainvoke({
        "working_dir": working_dir,
        "task_description": task,
        "base_ref": base_ref,
    })

    print("\n=== Results ===")
    print(f"branch:   {final.get('branch_name', '?')}")
    print(f"tests:    {final.get('test_summary', {})}")
    print(f"coverage: {final.get('coverage_summary', {})}")
    print(f"cost:     ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "usage: python -m langclaude.graphs.python_new_feature "
            '<working_dir> "task description" [base_ref]',
            file=sys.stderr,
        )
        sys.exit(2)
    cwd = sys.argv[1]
    task_desc = sys.argv[2]
    base = sys.argv[3] if len(sys.argv) >= 4 else "main"
    asyncio.run(main(cwd, task_desc, base))
