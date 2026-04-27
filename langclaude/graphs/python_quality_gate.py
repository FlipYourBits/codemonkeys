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
from typing import Any, Literal

from langclaude.nodes.base import Verbosity
from langclaude.pipeline import Pipeline

Mode = Literal["full", "diff"]


def build_pipeline(
    working_dir: str,
    *,
    mode: Mode = "diff",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    config: dict[str, dict[str, Any]] = {}
    extra_state: dict[str, str] = {"base_ref": base_ref}

    if mode == "diff":
        for node in ("python_coverage", "code_review", "security_audit", "docs_review"):
            config[node] = {"mode": "diff"}

    config["resolve_findings"] = {
        "requires": [
            "code_review",
            "security_audit",
            "docs_review",
            "python_dependency_audit",
        ],
    }
    config["python_lint_2"] = {"requires": ["python_lint"]}

    return Pipeline(
        working_dir=working_dir,
        steps=[
            "python_lint",
            "python_format",
            "python_coverage",
            "python_test",
            "python_dependency_audit",
            "code_review",
            "security_audit",
            "docs_review",
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
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(
        working_dir, mode=mode, base_ref=base_ref, verbosity=verbosity
    )
    final = await pipeline.run()

    if pipeline._display is not None:
        pipeline._display.print_results(final.get("node_costs", {}))
    else:
        from langclaude.display import Display
        Display(steps=[], title="Quality Gate Results", live=False).print_results(final.get("node_costs", {}))


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
