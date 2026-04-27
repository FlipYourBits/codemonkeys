"""Full Python repository review workflow.

Runs all review nodes in parallel against the entire repo. Read-only
(default allow/deny) — no edits.

Run with:

    python -m langclaude.graphs.python_full_repo_review /path/to/repo
"""

from __future__ import annotations

import asyncio
import sys

from langclaude.pipeline import Pipeline


def build_pipeline(working_dir: str, *, verbose: bool = True) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        steps=[
            [
                "ruff_fix",
                ["pytest", "coverage"],
                "code_review",
                "security_audit",
                "docs_review",
                "dependency_audit",
            ],
        ],
        config={
            "ruff_fix": {"fix": False, "fail_on_findings": False},
            "coverage": {"mode": "full"},
            "code_review": {"mode": "full"},
            "security_audit": {"mode": "full"},
            "docs_review": {"mode": "full"},
        },
        verbose=verbose,
    )


async def main(working_dir: str) -> None:
    pipeline = build_pipeline(working_dir)
    final = await pipeline.run()

    print("\n=== Full Repo Review ===")
    print(f"tests:      {str(final.get('test_findings', '<none>'))[:200]}")
    print(f"coverage:   {str(final.get('coverage_findings', '<none>'))[:200]}")
    print(f"dep vulns:  {str(final.get('dep_findings', '<none>'))[:200]}")
    print(f"review:     {str(final.get('review_findings', '<none>'))[:200]}")
    print(f"security:   {str(final.get('security_findings', '<none>'))[:200]}")
    print(f"docs:       {str(final.get('docs_findings', '<none>'))[:200]}")
    print(f"cost:       ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python -m langclaude.graphs.python_full_repo_review <working_dir>",
            file=sys.stderr,
        )
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
