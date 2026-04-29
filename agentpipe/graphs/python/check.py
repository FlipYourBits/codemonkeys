"""Python code quality check pipeline.

    ensure_tools → lint → format
        → [test, code_review, security, docs, dep_audit, type_check]
        → resolve_findings → lint

Run with:

    agentpipe python check /path/to/repo
    agentpipe python check /path/to/repo --no-interactive
    agentpipe python check /path/to/repo --verbosity silent

    python3 -m agentpipe.graphs.python.check .
    python3 -m agentpipe.graphs.python.check . --no-interactive --verbosity silent
"""

from __future__ import annotations

import argparse
import asyncio

from agentpipe.nodes.base import Verbosity
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.docs_review import DocsReview
from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit
from agentpipe.nodes.python_ensure_tools import PythonEnsureTools
from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_test import PythonTest
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_type_check import PythonTypeCheck
from agentpipe.nodes.resolve_findings import ResolveFindings
from agentpipe.pipeline import Pipeline


def build_pipeline(
    working_dir: str,
    *,
    base_ref: str = "main",
    interactive: bool = True,
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    python_ensure_tools = PythonEnsureTools()
    python_lint = PythonLint()
    python_format = PythonFormat()
    python_test = PythonTest()
    python_code_review = PythonCodeReview(base_ref=base_ref)
    python_security_audit = PythonSecurityAudit(base_ref=base_ref)
    docs_review = DocsReview(base_ref=base_ref)
    python_dependency_audit = PythonDependencyAudit()
    python_type_check = PythonTypeCheck()
    resolve_findings = ResolveFindings(
        interactive=interactive,
        reads_from=[
            python_test,
            python_code_review,
            python_security_audit,
            docs_review,
            python_dependency_audit,
            python_type_check,
        ],
    )
    python_lint_final = PythonLint()

    return Pipeline(
        working_dir=working_dir,
        steps=[
            python_ensure_tools,
            python_lint,
            python_format,
            [
                python_test,
                python_code_review,
                python_security_audit,
                docs_review,
                python_dependency_audit,
                python_type_check,
            ],
            resolve_findings,
            python_lint_final,
        ],
        verbosity=verbosity,
    )


async def main(
    working_dir: str,
    base_ref: str = "main",
    interactive: bool = True,
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(
        working_dir,
        base_ref=base_ref,
        interactive=interactive,
        verbosity=verbosity,
    )
    await pipeline.run()
    pipeline.print_results()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Python code quality check pipeline")
    parser.add_argument(
        "working_dir", nargs="?", default=".", help="Path to the repository root"
    )
    parser.add_argument("--base-ref", default="main", help="Git ref to diff against")
    parser.add_argument(
        "--no-interactive", action="store_true", help="Auto-fix HIGH+ without prompting"
    )
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.working_dir,
            base_ref=args.base_ref,
            interactive=not args.no_interactive,
            verbosity=Verbosity(args.verbosity),
        )
    )
