"""Python feature implementation workflow.

End-to-end graph: creates a branch, implements, lints, runs all review
nodes in parallel (each self-contained with fixing enabled), final lint,
and commits.

Run with:

    python -m langclaude.graphs.python_new_feature /path/to/repo "add a retry decorator"
"""

from __future__ import annotations

import asyncio
import shlex
import sys

from langclaude.nodes.base import ShellNode
from langclaude.pipeline import Pipeline


def _commit_node(**kwargs) -> ShellNode:
    return ShellNode(
        name="commit",
        command=lambda s: [
            "bash",
            "-c",
            "git add -A && git commit -m "
            + shlex.quote(f"feat: {s.get('task_description', 'implement feature')}"),
        ],
        output_key="last_result",
        check=True,
    )


def build_pipeline(
    working_dir: str,
    task: str,
    *,
    base_ref: str = "main",
    verbose: bool = True,
) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        task=task,
        steps=[
            "new_branch",
            "implement_feature",
            "ruff_fix",
            "ruff_fmt",
            [
                "pytest",
                "coverage",
                "code_review",
                "security_audit",
                "docs_review",
                "dependency_audit",
            ],
            ("ruff_final", "ruff_fix"),
            "custom/commit",
        ],
        extra_skills=["python-clean-code"],
        config={
            "pytest": {
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "coverage": {
                "mode": "diff",
                "base_ref_key": "base_ref",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "code_review": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "security_audit": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "docs_review": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "dependency_audit": {
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": [
                    "Bash(rm -rf*)",
                    "Bash(rm*)",
                    "Bash(git push*)",
                    "Bash(git commit*)",
                    "Bash(git reset*)",
                ],
            },
            "ruff_final": {"name": "ruff_final", "output_key": "ruff_final_output"},
        },
        custom_nodes={"custom/commit": _commit_node},
        verbose=verbose,
        extra_state={"base_ref": base_ref},
    )


async def main(working_dir: str, task: str, base_ref: str = "main") -> None:
    pipeline = build_pipeline(working_dir, task, base_ref=base_ref)
    final = await pipeline.run()

    print("\n=== Results ===")
    print(f"branch:   {final.get('branch_name', '?')}")
    print(f"tests:    {final.get('test_findings', '?')[:200]}")
    print(f"coverage: {final.get('coverage_findings', '?')[:200]}")
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
