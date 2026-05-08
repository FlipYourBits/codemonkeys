"""CLI fixer — load findings, pick which to fix, run fixer agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from codemonkeys.agents.fixer import FixItem, FixResult, make_fixer
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import RunResult, make_log_dir
from codemonkeys.display.formatting import severity_style
from codemonkeys.display.logger import FileLogger
from codemonkeys.display.stdout import fan_out, make_stdout_printer

console = Console()


def _load_findings(path: Path) -> list[FixItem]:
    """Load findings from a JSON file, auto-detecting format."""
    raw = json.loads(path.read_text())

    items: list[dict] = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if "results" in raw:
            items = raw["results"]
        elif "findings" in raw:
            items = raw["findings"]
        else:
            items = [raw]

    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "title" not in item and "description" not in item:
            continue
        findings.append(
            FixItem(
                file=item.get("file"),
                line=item.get("line"),
                severity=item.get("severity"),
                category=item.get("category"),
                title=item.get("title", item.get("description", "")[:80]),
                description=item.get("description", ""),
                suggestion=item.get("suggestion"),
            )
        )
    return findings


def _display_findings(items: list[FixItem]) -> None:
    table = Table(
        title="Findings",
        title_style="bold",
        show_lines=True,
        expand=True,
        highlight=False,
    )
    table.add_column("#", width=4, justify="right", no_wrap=True)
    table.add_column("Sev", width=6, justify="center", no_wrap=True)
    table.add_column("Location", width=30, no_wrap=True)
    table.add_column("Issue", ratio=3)
    table.add_column("Suggestion", ratio=2)

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    sorted_items = sorted(
        enumerate(items, 1),
        key=lambda x: severity_order.get((x[1].severity or "").lower(), 9),
    )

    for idx, item in sorted_items:
        sev = ""
        if item.severity:
            style = severity_style(item.severity)
            sev = f"[{style}]{item.severity.upper()}[/{style}]"

        loc = ""
        if item.file:
            loc = escape(item.file)
            if item.line:
                loc += f":{item.line}"

        issue = f"[bold]{escape(item.title)}[/bold]"
        if item.description and item.description != item.title:
            issue += f"\n{escape(item.description)}"

        suggestion = escape(item.suggestion) if item.suggestion else ""
        table.add_row(str(idx), sev, loc, issue, suggestion)

    console.print(table)


def _prompt_selection(count: int) -> list[int] | None:
    """Prompt user to select findings. Returns 0-based indices or None to quit."""
    console.print()
    response = console.input(
        "[bold]Fix:[/bold] [dim][a]ll, [1,2,3] specific, [q]uit[/dim] > "
    )
    response = response.strip().lower()

    if response in ("q", "quit", ""):
        return None
    if response in ("a", "all"):
        return list(range(count))

    indices = []
    for part in response.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
            if 1 <= n <= count:
                indices.append(n - 1)
            else:
                console.print(f"[yellow]Skipping {n} — out of range[/yellow]")
        except ValueError:
            console.print(f"[yellow]Skipping '{part}' — not a number[/yellow]")
    return indices if indices else None


def _print_result(result: RunResult) -> None:
    if result.error:
        console.print(f"\n[red]Fixer error: {result.error}[/red]")
        return

    if not isinstance(result.output, FixResult):
        console.print("\n[yellow]No structured result from fixer.[/yellow]")
        return

    fix = result.output
    console.print()
    if fix.applied:
        console.print(f"[green]Applied ({len(fix.applied)}):[/green]")
        for title in fix.applied:
            console.print(f"  [green]+[/green] {escape(title)}")
    if fix.skipped:
        console.print(f"[yellow]Skipped ({len(fix.skipped)}):[/yellow]")
        for reason in fix.skipped:
            console.print(f"  [yellow]-[/yellow] {escape(reason)}")
    console.print(f"\n[dim]{fix.summary}[/dim]")


async def run_fix(
    items: list[FixItem], model: str = "opus"
) -> RunResult:
    """Run the fixer agent on selected findings."""
    agent = make_fixer(items, model=model)

    log_dir = make_log_dir("fix")

    file_logger = FileLogger(log_dir / "fix_events.jsonl")
    stdout_printer = make_stdout_printer()
    on_event = fan_out(stdout_printer, file_logger.handle)

    console.print(f"[dim]Logging to {log_dir}/[/dim]\n")

    try:
        result = await run_agent(
            agent, "Apply the fixes described in your system prompt.", on_event=on_event
        )
    finally:
        file_logger.close()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix code issues from review/audit findings"
    )
    parser.add_argument(
        "findings",
        type=Path,
        help="Path to findings JSON file",
    )
    parser.add_argument(
        "--model",
        default="opus",
        choices=["haiku", "sonnet", "opus"],
        help="Model to use (default: opus)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="fix_all",
        help="Fix all findings without prompting",
    )

    args = parser.parse_args()

    if not args.findings.exists():
        console.print(f"[red]File not found: {args.findings}[/red]")
        sys.exit(1)

    items = _load_findings(args.findings)
    if not items:
        console.print("[yellow]No findings found in file.[/yellow]")
        sys.exit(0)

    _display_findings(items)

    if args.fix_all:
        selected_indices = list(range(len(items)))
    else:
        selected_indices = _prompt_selection(len(items))

    if selected_indices is None:
        console.print("[dim]Nothing selected.[/dim]")
        sys.exit(0)

    selected = [items[i] for i in selected_indices]
    console.print(
        f"\n[bold]Fixing {len(selected)} finding(s) [{args.model}][/bold]"
    )

    result = asyncio.run(run_fix(selected, model=args.model))
    _print_result(result)

    sys.exit(1 if result.error else 0)


if __name__ == "__main__":
    main()
