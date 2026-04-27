"""Python code quality gate.

Sequential pipeline: lint, format, test, coverage, code review,
security audit, doc review, dependency audit, final lint.

Run with:

    python -m langclaude.graphs.python_quality_gate /path/to/repo
    python -m langclaude.graphs.python_quality_gate /path/to/repo --mode diff --base-ref main
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal

from langclaude.nodes.base import Verbosity
from langclaude.pipeline import Pipeline

Mode = Literal["full", "diff"]


def build_pipeline(
    working_dir: str,
    *,
    mode: Mode = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    config: dict[str, dict[str, str]] = {}
    extra_state: dict[str, str] = {"base_ref": base_ref}

    if mode == "diff":
        for node in ("python_coverage", "code_review", "security_audit", "docs_review"):
            config[node] = {"mode": "diff"}

    return Pipeline(
        working_dir=working_dir,
        steps=[
            "python_lint",
            "python_format",
            "python_test",
            "python_coverage",
            "code_review",
            "security_audit",
            "docs_review",
            "dependency_audit",
            "python_lint",
        ],
        config=config,
        verbosity=verbosity,
        extra_state=extra_state,
    )


async def main(
    working_dir: str,
    mode: str = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(working_dir, mode=mode, base_ref=base_ref, verbosity=verbosity)
    final = await pipeline.run()

    print("\n=== Quality Gate Results ===")
    print(f"tests:    {str(final.get('python_test', '?'))[:200]}")
    print(f"coverage: {str(final.get('python_coverage', '?'))[:200]}")
    print(f"cost:     ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Python quality gate pipeline.",
    )
    parser.add_argument("working_dir", help="Path to the repository root")
    parser.add_argument(
        "--mode",
        choices=["full", "diff"],
        default="full",
        help="Scan entire repo (full) or only changes vs base ref (diff). Default: full",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Git ref to diff against when --mode=diff (default: main)",
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
            mode=args.mode,
            base_ref=args.base_ref,
            verbosity=Verbosity(args.verbosity),
        ),
    )
