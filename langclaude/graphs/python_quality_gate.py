"""Python code quality gate.

Runs lint and format first (they modify files), then fans out six
review/audit nodes in parallel, collects findings into an interactive
resolver, and finishes with a final lint pass.

    lint → format → [test, coverage, code_review, security, docs, dep_audit]
        → resolve_findings → lint

Defaults to diff mode (only changes vs base ref). Use --mode full to
scan the entire repo.

Run with:

    python -m langclaude.graphs.python_quality_gate /path/to/repo
    python -m langclaude.graphs.python_quality_gate /path/to/repo --mode full
    python -m langclaude.graphs.python_quality_gate /path/to/repo --no-interactive
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any, Literal

from langclaude.models import HAIKU_4_5, SONNET_4_6
from langclaude.nodes.base import Verbosity
from langclaude.pipeline import Pipeline

Mode = Literal["full", "diff"]


def build_pipeline(
    working_dir: str,
    *,
    mode: Mode = "diff",
    base_ref: str = "main",
    interactive: bool = True,
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    diff = {"mode": "diff"} if mode == "diff" else {}

    return Pipeline(
        working_dir=working_dir,
        steps=[
            "python_lint",
            "python_format",
            [
                "python_test",
                "python_coverage",
                "code_review",
                "security_audit",
                "docs_review",
                "python_dependency_audit",
            ],
            "resolve_findings",
            "python_lint",
        ],
        config={
            "python_test": {"model": SONNET_4_6},
            "python_coverage": {"model": SONNET_4_6, **diff},
            "code_review": {**diff},
            "security_audit": {**diff},
            "docs_review": {"model": SONNET_4_6, **diff},
            "python_dependency_audit": {"model": HAIKU_4_5},
            "resolve_findings": {
                "interactive": interactive,
                "requires": [
                    "python_test",
                    "python_coverage",
                    "code_review",
                    "security_audit",
                    "docs_review",
                    "python_dependency_audit",
                ],
            },
            "python_lint_2": {"requires": ["python_lint"]},
        },
        verbosity=verbosity,
        extra_state={"base_ref": base_ref},
    )


async def main(
    working_dir: str,
    mode: str = "diff",
    base_ref: str = "main",
    interactive: bool = True,
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(
        working_dir,
        mode=mode,
        base_ref=base_ref,
        interactive=interactive,
        verbosity=verbosity,
    )
    await pipeline.run()
    pipeline.print_results()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Python quality gate pipeline.",
    )
    parser.add_argument(
        "working_dir",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "diff"],
        default="diff",
        help="Scan only changes vs base ref (diff) or entire repo (full). Default: diff",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Git ref to diff against when --mode=diff (default: main)",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Auto-fix HIGH+ issues without prompting (default: interactive)",
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
            interactive=not args.no_interactive,
            verbosity=Verbosity(args.verbosity),
        ),
    )
