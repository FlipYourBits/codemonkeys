"""CLI review pipeline — discover files, run parallel reviewers, print findings."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from codemonkeys.agents.python_file_reviewer import (
    FileFindings,
    Finding,
    make_python_file_reviewer,
)
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import RunResult
from codemonkeys.display.live import LiveDisplay

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


def _severity_style(severity: str) -> str:
    return {
        "high": "bold red",
        "medium": "yellow",
        "low": "blue",
        "info": "dim",
    }.get(severity.lower(), "white")


def _print_summary(all_findings: list[Finding], total_cost: float) -> None:
    if not all_findings:
        console.print("\n[green]No findings.[/green]")
        return

    by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    console.print()
    for file_path, findings in sorted(by_file.items()):
        console.print(f"[bold]{file_path}[/bold]")
        table = Table(show_header=True, padding=(0, 1), box=None)
        table.add_column("Line", style="dim", width=6)
        table.add_column("Severity", width=8)
        table.add_column("Category", width=10)
        table.add_column("Title")

        for finding in sorted(findings, key=lambda f: f.line or 0):
            line_str = str(finding.line) if finding.line else "-"
            style = _severity_style(finding.severity)
            table.add_row(
                line_str,
                f"[{style}]{finding.severity}[/{style}]",
                finding.category,
                finding.title,
            )

        console.print(table)

        for finding in sorted(findings, key=lambda f: f.line or 0):
            if finding.description:
                line_prefix = f"L{finding.line}: " if finding.line else ""
                style = _severity_style(finding.severity)
                console.print(
                    f"  [{style}]{line_prefix}{finding.description}[/{style}]"
                )
                if finding.suggestion:
                    console.print(f"    [dim]Suggestion: {finding.suggestion}[/dim]")
        console.print()

    high = sum(1 for f in all_findings if f.severity.lower() == "high")
    medium = sum(1 for f in all_findings if f.severity.lower() == "medium")
    low = sum(1 for f in all_findings if f.severity.lower() == "low")
    console.print(
        f"[bold]Totals:[/bold] {len(all_findings)} findings "
        f"([red]{high} high[/red], [yellow]{medium} medium[/yellow], [blue]{low} low[/blue]) "
        f"| Cost: ${total_cost:.4f}"
    )


async def run_review(files: list[str], model: str = "sonnet") -> int:
    """Run parallel file reviewers and print findings. Returns exit code."""
    batches = _batch(files, BATCH_SIZE)
    agents = [make_python_file_reviewer(batch, model=model) for batch in batches]

    console.print(
        f"\n[bold]Reviewing {len(files)} file(s) in {len(batches)} batch(es) [{model}][/bold]\n"
    )

    display = LiveDisplay()
    display.start()

    try:
        results: list[RunResult] = await asyncio.gather(
            *[
                run_agent(agent, "Review the listed files.", on_event=display.handle)
                for agent in agents
            ]
        )
    finally:
        display.stop()

    all_findings: list[Finding] = []
    total_cost = 0.0
    for result in results:
        total_cost += result.cost_usd
        if result.error:
            console.print(f"[red]Agent error: {result.error}[/red]")
            continue
        if isinstance(result.output, FileFindings):
            all_findings.extend(result.output.results)

    _print_summary(all_findings, total_cost)

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

    exit_code = asyncio.run(run_review(files, model=args.model))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
