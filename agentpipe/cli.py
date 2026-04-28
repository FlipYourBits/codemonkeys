"""CLI entry point: agentpipe <language> <action> [options]."""

from __future__ import annotations

import argparse
import asyncio

from agentpipe.nodes.base import Verbosity


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "working_dir",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Git ref to diff against (default: main)",
    )
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
        help="Output verbosity (default: normal)",
    )


def _run_check(args: argparse.Namespace) -> None:
    from agentpipe.graphs.python.check import main

    asyncio.run(
        main(
            args.working_dir,
            base_ref=args.base_ref,
            interactive=not args.no_interactive,
            verbosity=Verbosity(args.verbosity),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agentpipe",
        description="Deterministic AI pipelines powered by the Claude Agent SDK.",
    )
    lang_parsers = parser.add_subparsers(dest="language", required=True)

    # -- python ---------------------------------------------------------
    py_parser = lang_parsers.add_parser("python", help="Python pipelines")
    action_parsers = py_parser.add_subparsers(dest="action", required=True)

    # python check
    check_parser = action_parsers.add_parser(
        "check",
        help="Run the code quality gate (diff-only)",
    )
    _add_common_args(check_parser)
    check_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Auto-fix HIGH+ issues without prompting",
    )
    check_parser.set_defaults(func=_run_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
