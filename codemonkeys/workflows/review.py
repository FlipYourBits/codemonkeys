"""Code review workflow — dispatches review agents and optionally fixes findings.

Usage:
    .venv/bin/python -m codemonkeys.workflows.review /path/to/repo
    .venv/bin/python -m codemonkeys.workflows.review . --no-fix
    .venv/bin/python -m codemonkeys.workflows.review . --file src/main.py
    .venv/bin/python -m codemonkeys.workflows.review . -o results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table
from rich.text import Text

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
)

from codemonkeys.agents import (
    CODE_REVIEWER,
    DEPENDENCY_AUDITOR,
    DOCS_REVIEWER,
    FIXER,
    LINTER,
    SECURITY_AUDITOR,
    TEST_RUNNER,
    TYPE_CHECKER,
)
from codemonkeys.runner import AgentRunner


# ── Output models ────────────────────────────────────────────────


class Finding(BaseModel):
    file: str = Field(description="File path relative to repo root")
    line: int = Field(description="Line number")
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Issue severity")
    source: str = Field(description="Which agent found this")
    category: str = Field(description="e.g. logic_error, test_failure, vulnerability")
    description: str = Field(description="What the issue is")
    recommendation: str = Field(description="How to fix it")


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(description="Brief overall assessment")
    tests_passed: bool = Field(description="Whether all tests passed")


# ── Coordinator prompt ───────────────────────────────────────────

COORDINATOR_PROMPT = """\
You are a code quality coordinator. You have these review agents:

1. "code_reviewer" — static code review (logic errors, leaks, dead code)
2. "test_runner" — runs pytest and analyzes failures
3. "security_auditor" — finds security vulnerabilities
4. "type_checker" — runs mypy and reports type errors
5. "linter" — runs ruff and reports lint violations
6. "dependency_auditor" — scans for known CVEs via pip-audit
7. "docs_reviewer" — finds documentation drift against code

Your job:
1. Dispatch ALL review agents. Always dispatch all of them, never skip any.
2. Wait for their results.
3. Combine ALL findings into the structured output format.

Include every finding from every agent — do not summarize or drop any.

If a fixer agent is available and you are asked to fix issues, dispatch it
with the specific findings to fix."""


# ── Coordinator ──────────────────────────────────────────────────


class ReviewCoordinator:

    def __init__(
        self,
        working_dir: str,
        *,
        allow_fix: bool = True,
        model: str = "sonnet",
    ) -> None:
        self.working_dir = working_dir
        self.allow_fix = allow_fix
        self.model = model
        self._out = Console()

    def _parse_result(self, msg: ResultMessage) -> ReviewResult | None:
        structured = getattr(msg, "structured_output", None)
        if structured:
            if isinstance(structured, dict):
                return ReviewResult.model_validate(structured)
            if isinstance(structured, str):
                return ReviewResult.model_validate_json(structured)

        text = getattr(msg, "result", "") or ""
        if not text:
            return None
        try:
            return ReviewResult.model_validate_json(text)
        except Exception:
            pass
        try:
            match = re.search(r"```json?\s*\n([\s\S]*?)\n\s*```", text)
            if match:
                return ReviewResult.model_validate_json(match.group(1))
        except Exception:
            pass
        return None

    def _print_findings(self, findings: list[Finding]) -> None:
        if not findings:
            self._out.print("\n[green]No findings.[/green]")
            return

        severity_styles = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
        table = Table(show_header=True, expand=True, padding=(0, 1))
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Sev", width=8)
        table.add_column("Source", style="cyan", width=14)
        table.add_column("Location", width=30)
        table.add_column("Description")

        for i, f in enumerate(findings, 1):
            style = severity_styles.get(f.severity, "")
            table.add_row(
                str(i),
                Text(f.severity, style=style),
                f.source,
                f"{f.file}:{f.line}",
                f.description,
            )
        self._out.print(table)

    async def run(
        self,
        *,
        target_file: str | None = None,
        output_file: str | None = None,
    ) -> ReviewResult | None:
        agents = {
            "code_reviewer": CODE_REVIEWER,
            "test_runner": TEST_RUNNER,
            "security_auditor": SECURITY_AUDITOR,
            "type_checker": TYPE_CHECKER,
            "linter": LINTER,
            "dependency_auditor": DEPENDENCY_AUDITOR,
            "docs_reviewer": DOCS_REVIEWER,
        }
        if self.allow_fix:
            agents["fixer"] = FIXER

        review_options = ClaudeAgentOptions(
            system_prompt=COORDINATOR_PROMPT,
            model=self.model,
            cwd=self.working_dir,
            permission_mode="bypassPermissions",
            allowed_tools=["Agent"],
            agents=agents,
            output_format={"type": "json_schema", "schema": ReviewResult.model_json_schema()},
        )

        runner = AgentRunner(cwd=self.working_dir)

        if target_file:
            prompt = f"Review only the file {target_file}. Dispatch all review agents scoped to this file and combine their findings."
        else:
            prompt = "Run a full quality check on this repository. Dispatch all review agents and combine their findings."

        await runner.run(review_options, prompt)
        result_msg = runner.last_result

        review = self._parse_result(result_msg) if result_msg else None
        if review:
            self._out.print(f"\n{'---' * 20}")
            self._out.print(f"[bold]{review.summary}[/bold]")
            self._out.print(f"Tests passed: {'yes' if review.tests_passed else 'no'}")
            self._print_findings(review.findings)
            if output_file:
                Path(output_file).write_text(
                    review.model_dump_json(indent=2), encoding="utf-8"
                )
                self._out.print(f"\nResults written to {output_file}")
        elif result_msg:
            self._out.print(f"\n{'---' * 20}")
            self._out.print(getattr(result_msg, "result", "") or "(no output)")

        if not self.allow_fix or not review or not review.findings:
            return review

        # Fix phase
        self._out.print(f"\n{'---' * 20}")
        choice = input("Fix issues? [all / high+ / none]: ").strip().lower()
        if choice in ("none", "n", "no", "q", ""):
            return review

        if choice in ("high", "high+"):
            to_fix = [f for f in review.findings if f.severity == "HIGH"]
        else:
            to_fix = review.findings

        fix_options = ClaudeAgentOptions(
            system_prompt=COORDINATOR_PROMPT,
            model=self.model,
            cwd=self.working_dir,
            permission_mode="bypassPermissions",
            allowed_tools=["Agent"],
            agents={"fixer": FIXER},
        )
        findings_json = json.dumps([f.model_dump() for f in to_fix], indent=2)
        fix_text = await runner.run(
            fix_options,
            f"Fix these {len(to_fix)} findings. Dispatch the fixer agent with this list:\n\n{findings_json}",
        )
        if fix_text:
            self._out.print(f"\n{'---' * 20}")
            self._out.print(fix_text)

        return review


async def main(
    working_dir: str,
    allow_fix: bool = True,
    output_file: str | None = None,
    target_file: str | None = None,
) -> None:
    coordinator = ReviewCoordinator(working_dir, allow_fix=allow_fix)
    await coordinator.run(target_file=target_file, output_file=output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiagent code review")
    parser.add_argument("working_dir", nargs="?", default=".", help="Repo path")
    parser.add_argument("--no-fix", action="store_true", help="Skip fix prompt")
    parser.add_argument("-o", "--output", help="Write structured results to JSON file")
    parser.add_argument("--file", help="Review a single file instead of the whole repo")
    args = parser.parse_args()
    asyncio.run(main(args.working_dir, allow_fix=not args.no_fix, output_file=args.output, target_file=args.file))
