"""Temporary demo: lint → format → test → resolve_findings → lint.

Run with:
    python -m agentpipe.graphs.demo2 /path/to/repo
"""

from __future__ import annotations

import argparse
import asyncio

from agentpipe.nodes.base import Verbosity
from agentpipe.pipeline import Pipeline


def build_pipeline(
    working_dir: str,
    *,
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        task="demo lint/format/test pipeline",
        steps=[
            "python_lint",
            "python_format",
            "python_test",
            "resolve_findings",
            "python_lint",
        ],
        config={
            "resolve_findings": {
                "interactive": True,
                "requires": ["python_test"],
            },
            "python_lint_2": {"requires": ["python_lint"]},
        },
        verbosity=verbosity,
    )


async def main(working_dir: str, verbosity: Verbosity = Verbosity.normal) -> None:
    pipeline = build_pipeline(working_dir, verbosity=verbosity)
    await pipeline.run()
    pipeline.print_results()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demo: lint/format/test pipeline")
    parser.add_argument("working_dir", nargs="?", default=".")
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
    )
    args = parser.parse_args()
    asyncio.run(main(args.working_dir, verbosity=Verbosity(args.verbosity)))
