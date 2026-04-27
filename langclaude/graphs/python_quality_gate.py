"""Python code quality gate.

Pipeline shape:

    lint → format → [test, coverage, code_review, security, docs, dep_audit]
        → resolve_findings (interactive) → lint

Run with:

    python -m langclaude.graphs.python_quality_gate /path/to/repo
    python -m langclaude.graphs.python_quality_gate /path/to/repo --mode diff --base-ref main
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
    config: dict[str, dict[str, Any]] = {
        "python_test": {
            "model": SONNET_4_6,
            "max_turns": 10,
            "max_budget_usd": 0.50,
        },
        "python_coverage": {
            "model": SONNET_4_6,
            "max_turns": 8,
            "max_budget_usd": 0.30,
        },
        "code_review": {
            "max_turns": 6,
            "max_budget_usd": 0.50,
        },
        "security_audit": {
            "max_turns": 6,
            "max_budget_usd": 0.50,
        },
        "docs_review": {
            "model": SONNET_4_6,
            "max_turns": 5,
            "max_budget_usd": 0.20,
        },
        "python_dependency_audit": {
            "model": HAIKU_4_5,
            "max_turns": 5,
            "max_budget_usd": 0.10,
        },
        "resolve_findings": {
            "interactive": interactive,
            "max_turns": 15,
            "max_budget_usd": 1.00,
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
    }
    extra_state: dict[str, str] = {"base_ref": base_ref}

    if mode == "diff":
        for node in ("python_coverage", "code_review", "security_audit", "docs_review"):
            config[node]["mode"] = "diff"

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
        config=config,
        verbosity=verbosity,
        extra_state=extra_state,
    )


async def main(
    working_dir: str,
    mode: str = "full",
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
    final = await pipeline.run()

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
