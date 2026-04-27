"""Python feature implementation workflow.

End-to-end graph: creates a branch, plans the feature interactively,
implements with user review, lints, runs all review nodes in parallel
(each self-contained with fixing enabled), final lint, and commits.

Run with:

    python -m langclaude.graphs.python_new_feature /path/to/repo "add a retry decorator"
"""

from __future__ import annotations

import argparse
import asyncio

from langclaude.nodes.base import Verbosity
from langclaude.pipeline import Pipeline


def build_pipeline(
    working_dir: str,
    task: str,
    *,
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        task=task,
        steps=[
            "git_new_branch",
            "python_plan_feature",
            "python_implement_feature",
            "python_lint",
            "python_format",
            "python_test",
            "python_coverage",
            "code_review",
            "security_audit",
            "docs_review",
            "dependency_audit",
            "python_lint",
            "git_commit",
        ],
        config={
            "python_coverage": {"mode": "diff"},
            "code_review": {"mode": "diff"},
            "security_audit": {"mode": "diff"},
            "docs_review": {"mode": "diff"},
        },
        verbosity=verbosity,
        extra_state={"base_ref": base_ref},
    )


async def main(
    working_dir: str,
    task: str,
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(working_dir, task, base_ref=base_ref, verbosity=verbosity)
    final = await pipeline.run()

    print("\n=== Results ===")
    print(f"branch:   {final.get('git_new_branch', '?')}")
    print(f"tests:    {str(final.get('python_test', '?'))[:200]}")
    print(f"coverage: {str(final.get('python_coverage', '?'))[:200]}")
    print(f"cost:     ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Python new-feature pipeline.",
    )
    parser.add_argument("working_dir", help="Path to the repository root")
    parser.add_argument("task", help="Task description for the feature")
    parser.add_argument(
        "--base-ref", default="main", help="Git ref to diff against for certain nodes e.g. code_review (default: main)",
    )
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
        help="Output verbosity (default: normal)",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.working_dir,
            args.task,
            base_ref=args.base_ref,
            verbosity=Verbosity(args.verbosity),
        ),
    )
