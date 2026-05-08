"""CLI review pipeline — discover files, run parallel reviewers, print findings."""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from codemonkeys.agents.python_file_reviewer import (
    FileFindings,
    Finding,
    make_python_file_reviewer,
)
from codemonkeys.agents.review_auditor import (
    ReviewAudit,
    make_review_auditor,
)
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import RunResult
from codemonkeys.display.formatting import format_event_trace, severity_style
from codemonkeys.display.logger import FileLogger
from codemonkeys.display.stdout import fan_out, make_stdout_printer

BATCH_SIZE = 3
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".tox", ".mypy_cache"}

console = Console()


def _discover_files_explicit(paths: list[str]) -> list[str]:
    resolved = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            console.print(f"[yellow]Warning: {p} does not exist, skipping[/yellow]")
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*.py")):
                if not any(part in EXCLUDE_DIRS for part in child.parts):
                    resolved.append(str(child))
            continue
        if path.suffix != ".py":
            console.print(f"[yellow]Warning: {p} is not a .py file, skipping[/yellow]")
            continue
        resolved.append(str(path))
    return resolved


def _discover_files_diff() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True,
        text=True,
    )
    all_files = set(
        result.stdout.strip().splitlines() + staged.stdout.strip().splitlines()
    )
    return sorted(f for f in all_files if f.endswith(".py") and Path(f).exists())


def _discover_files_repo() -> list[str]:
    files = []
    for p in Path(".").rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        files.append(str(p))
    return sorted(files)


def _batch(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _print_summary(all_findings: list[Finding], total_cost: float) -> None:
    if not all_findings:
        console.print("\n[green]No findings.[/green]")
        return

    high = sum(1 for f in all_findings if f.severity.lower() == "high")
    medium = sum(1 for f in all_findings if f.severity.lower() == "medium")
    low = sum(1 for f in all_findings if f.severity.lower() == "low")

    console.print()
    console.rule(
        f"[bold]{len(all_findings)} findings[/bold] "
        f"([red]{high} high[/red], [yellow]{medium} medium[/yellow], [blue]{low} low[/blue]) "
        f"| Cost: ${total_cost:.4f}",
        style="dim",
    )

    by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}

    for file_path, findings in sorted(by_file.items()):
        table = Table(
            title=file_path,
            title_style="bold",
            show_lines=True,
            expand=True,
            highlight=False,
        )
        table.add_column("Sev", width=6, justify="center", no_wrap=True)
        table.add_column("Line", width=6, justify="right", no_wrap=True)
        table.add_column("Issue", ratio=3)
        table.add_column("Suggestion", ratio=2)

        sorted_findings = sorted(
            findings,
            key=lambda f: (severity_order.get(f.severity.lower(), 9), f.line or 0),
        )

        for finding in sorted_findings:
            style = severity_style(finding.severity)
            sev = f"[{style}]{finding.severity.upper()}[/{style}]"
            line_ref = str(finding.line) if finding.line else ""
            issue = f"[bold]{escape(finding.title)}[/bold]"
            if finding.description:
                issue += f"\n{escape(finding.description)}"
            suggestion = escape(finding.suggestion) if finding.suggestion else ""
            table.add_row(sev, line_ref, issue, suggestion)

        console.print()
        console.print(table)


def _verdict_style(verdict: str) -> str:
    return {"pass": "bold green", "warn": "bold yellow", "fail": "bold red"}.get(
        verdict.lower(), "white"
    )


def _print_audit_results(
    audit_results: list[tuple[str, RunResult]], total_audit_cost: float
) -> None:
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}

    verdicts: list[str] = []
    for _, r in audit_results:
        if isinstance(r.output, ReviewAudit):
            verdicts.append(r.output.verdict.lower())
    passes = verdicts.count("pass")
    warns = verdicts.count("warn")
    fails = verdicts.count("fail")

    console.print()
    console.rule(
        f"[bold]AUDIT[/bold] — "
        f"[bold]{len(audit_results)} audit(s)[/bold] "
        f"([green]{passes} pass[/green], [yellow]{warns} warn[/yellow], "
        f"[red]{fails} fail[/red]) "
        f"| Cost: ${total_audit_cost:.4f}",
        style="magenta",
    )

    for reviewer_name, result in audit_results:
        if result.error:
            console.print(
                f"\n  [red]{reviewer_name} — audit error: {result.error}[/red]"
            )
            continue
        if not isinstance(result.output, ReviewAudit):
            console.print(
                f"\n  [yellow]{reviewer_name} — no structured audit output[/yellow]"
            )
            continue

        audit = result.output
        vstyle = _verdict_style(audit.verdict)

        table = Table(
            title=f"{reviewer_name} — [{vstyle}]{audit.verdict.upper()}[/{vstyle}]",
            title_style="bold",
            caption=audit.summary,
            caption_style="dim",
            show_lines=True,
            expand=True,
            highlight=False,
        )
        table.add_column("Sev", width=6, justify="center", no_wrap=True)
        table.add_column("Category", width=14, no_wrap=True)
        table.add_column("Finding", ratio=3)
        table.add_column("Suggestion", ratio=2)

        if audit.findings:
            sorted_findings = sorted(
                audit.findings,
                key=lambda f: severity_order.get(f.severity.lower(), 9),
            )
            for f in sorted_findings:
                sev_style = severity_style(f.severity)
                sev = f"[{sev_style}]{f.severity.upper()}[/{sev_style}]"
                finding_text = f"[bold]{escape(f.title)}[/bold]"
                if f.description:
                    finding_text += f"\n{escape(f.description)}"
                suggestion = escape(f.suggestion) if f.suggestion else ""
                table.add_row(sev, f.category, finding_text, suggestion)
        else:
            table.add_row(
                "[green]--[/green]", "--", "[green]No issues found[/green]", ""
            )

        console.print()
        console.print(table)


def _make_log_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = Path(".codemonkeys") / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", name)


def _export_outputs(results: list[RunResult], log_dir: Path) -> None:
    for result in results:
        if result.output is None or result.agent_def is None:
            continue
        filename = _safe_filename(result.agent_def.name) + ".json"
        path = log_dir / filename
        path.write_text(result.output.model_dump_json(indent=2) + "\n")
        console.print(f"  [dim]{path}[/dim]")


async def run_review(
    files: list[str], model: str = "sonnet", audit: bool = False
) -> int:
    """Run parallel file reviewers and print findings. Returns exit code."""
    batches = _batch(files, BATCH_SIZE)
    agents = [make_python_file_reviewer(batch, model=model) for batch in batches]

    console.print(
        f"\n[bold]Reviewing {len(files)} file(s) in {len(batches)} batch(es) [{model}][/bold]\n"
    )

    log_dir = _make_log_dir()
    file_logger = FileLogger(log_dir / "events.jsonl")
    stdout_printer = make_stdout_printer()
    on_event = fan_out(stdout_printer, file_logger.handle)

    console.print(f"[dim]Logging to {log_dir}/[/dim]\n")

    try:
        results: list[RunResult] = await asyncio.gather(
            *[
                run_agent(agent, "Review the listed files.", on_event=on_event)
                for agent in agents
            ]
        )
    finally:
        file_logger.close()

    all_findings: list[Finding] = []
    total_cost = 0.0
    for result in results:
        total_cost += result.cost_usd
        if result.error:
            console.print(f"[red]Agent error: {result.error}[/red]")
            continue
        if isinstance(result.output, FileFindings):
            all_findings.extend(result.output.results)

    _export_outputs(results, log_dir)
    _print_summary(all_findings, total_cost)

    if audit:
        successful_results = [r for r in results if not r.error and r.agent_def]
        if not successful_results:
            console.print("\n[yellow]No successful reviews to audit.[/yellow]")
        else:
            console.print(
                f"\n[bold]Auditing {len(successful_results)} review(s) [{model}][/bold]\n"
            )
            audit_logger = FileLogger(log_dir / "audit_events.jsonl")
            audit_on_event = fan_out(stdout_printer, audit_logger.handle)

            try:
                audit_agents = []
                for r in successful_results:
                    ad = r.agent_def
                    assert ad is not None
                    trace = format_event_trace(r.events)
                    findings_json = r.output.model_dump_json(indent=2) if r.output else "null"
                    tools_str = ", ".join(ad.tools) if ad.tools else "(none)"
                    audit_agents.append(
                        make_review_auditor(
                            trace=trace,
                            findings_json=findings_json,
                            reviewer_name=ad.name,
                            reviewer_model=ad.model,
                            reviewer_tools=tools_str,
                            reviewer_prompt=ad.system_prompt,
                            model=model,
                        )
                    )
                audit_results_raw: list[RunResult] = await asyncio.gather(
                    *[
                        run_agent(a, "Audit this review.", on_event=audit_on_event)
                        for a in audit_agents
                    ]
                )
            finally:
                audit_logger.close()

            audit_pairs: list[tuple[str, RunResult]] = []
            total_audit_cost = 0.0
            for review_result, audit_result in zip(
                successful_results, audit_results_raw
            ):
                name = review_result.agent_def.name if review_result.agent_def else "?"
                audit_pairs.append((name, audit_result))
                total_audit_cost += audit_result.cost_usd

            _export_outputs(audit_results_raw, log_dir)
            _print_audit_results(audit_pairs, total_audit_cost)
            total_cost += total_audit_cost

    has_high = any(f.severity.lower() == "high" for f in all_findings)
    return 1 if has_high else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review Python files for quality and security"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--files", nargs="+", metavar="PATH", help="Explicit file paths to review"
    )
    mode.add_argument(
        "--diff", action="store_true", help="Review files changed in git diff"
    )
    mode.add_argument(
        "--repo", action="store_true", help="Review all Python files in the repo"
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["haiku", "sonnet", "opus"],
        help="Model to use (default: sonnet)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run audit agents to verify reviewer behavior",
    )

    args = parser.parse_args()

    if args.files:
        files = _discover_files_explicit(args.files)
    elif args.diff:
        files = _discover_files_diff()
    else:
        files = _discover_files_repo()

    if not files:
        console.print("[yellow]No Python files found to review.[/yellow]")
        sys.exit(0)

    for f in files:
        console.print(f"  [dim]{f}[/dim]")

    exit_code = asyncio.run(run_review(files, model=args.model, audit=args.audit))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
