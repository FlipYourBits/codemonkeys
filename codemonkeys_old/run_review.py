"""CLI review pipeline — thin wrapper over the workflow engine.

Run from the project root:
    uv run python -m codemonkeys.run_review --diff
    uv run python -m codemonkeys.run_review --files codemonkeys/core/runner.py
    uv run python -m codemonkeys.run_review --auto-fix
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from codemonkeys.core.sandbox import restrict
from codemonkeys.workflows.compositions import (
    ReviewConfig,
    make_diff_workflow,
    make_files_workflow,
    make_repo_workflow,
    make_post_feature_workflow,
)
from codemonkeys.workflows.display import WorkflowDisplay
from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType
from codemonkeys.workflows.phases import WorkflowContext

console = Console()


def _init_log_dir(cwd: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = cwd / ".codemonkeys" / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _select_mode() -> str:
    console.print(
        Panel(
            "[bold]Select review scope[/bold]\n\n"
            "  [bold]1[/bold]  git diff — changed files vs HEAD\n"
            "  [bold]2[/bold]  full repo — all .py files\n",
            border_style="blue",
            padding=(1, 2),
        )
    )
    choice = console.input("  [bold]>[/bold] ").strip()
    if choice == "2":
        return "repo"
    return "diff"


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.files:
        return "files"
    if args.diff:
        return "diff"
    if args.repo:
        return "repo"
    if args.deep_clean:
        return "deep_clean"
    return _select_mode()


def _pick_workflow(config: ReviewConfig):
    if config.mode == "files":
        return make_files_workflow(auto_fix=config.auto_fix)
    if config.mode == "diff":
        return make_diff_workflow(auto_fix=config.auto_fix)
    if config.mode == "post_feature":
        return make_post_feature_workflow(auto_fix=config.auto_fix)
    if config.mode == "deep_clean":
        from codemonkeys.workflows.compositions import make_deep_clean_workflow

        return make_deep_clean_workflow()
    return make_repo_workflow(auto_fix=config.auto_fix)


def _handle_refactor_gate(
    engine: WorkflowEngine, display: WorkflowDisplay, phase_name: str
) -> None:
    display.pause()
    step_label = phase_name.replace("refactor_", "").replace("_", " ").title()
    console.print(
        Panel(
            f"[bold]Refactor Step: {step_label}[/bold]\n\n"
            '  [dim]"approve" to proceed with this refactoring[/dim]\n'
            '  [dim]"skip" to skip this step[/dim]',
            border_style="yellow",
            padding=(1, 2),
        )
    )
    user_input = console.input("  [bold]>[/bold] ").strip()
    display.resume()

    if not user_input or user_input.lower() == "skip":
        engine.resolve_gate("skip")
    else:
        engine.resolve_gate("approve")


def _handle_triage_gate(engine: WorkflowEngine, display: WorkflowDisplay) -> None:
    display.pause()
    console.print(
        Panel(
            "[bold]Enter what you want to fix[/bold] (natural language)\n\n"
            '  [dim]"fix everything"[/dim]\n'
            '  [dim]"fix the high severity ones"[/dim]\n'
            '  [dim]"fix all except style issues"[/dim]\n'
            '  [dim]"just fix #2 and #5"[/dim]\n'
            '  [dim]"skip" to skip fixes[/dim]',
            border_style="blue",
            padding=(1, 2),
        )
    )
    user_input = console.input("  [bold]>[/bold] ").strip()
    display.resume()

    if not user_input or user_input.lower() == "skip":
        engine.resolve_gate([])
    else:
        engine.resolve_gate(user_input)


async def main_async(args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    restrict(cwd)
    log_dir = _init_log_dir(cwd)

    mode = _resolve_mode(args)
    config = ReviewConfig(
        mode=mode,
        target_files=args.files,
        auto_fix=args.auto_fix,
        graph=getattr(args, "graph", False),
    )

    emitter = EventEmitter()
    workflow = _pick_workflow(config)
    display = WorkflowDisplay(workflow, emitter)
    engine = WorkflowEngine(emitter)

    def on_waiting(_: EventType, payload: object) -> None:
        phase_name = getattr(payload, "phase", "")
        if phase_name.startswith("refactor_"):
            _handle_refactor_gate(engine, display, phase_name)
        else:
            _handle_triage_gate(engine, display)

    emitter.on(EventType.WAITING_FOR_USER, on_waiting)

    ctx = WorkflowContext(
        cwd=str(cwd),
        run_id=str(log_dir.relative_to(cwd / ".codemonkeys")),
        config=config,
        log_dir=log_dir,
    )

    console.print(
        Panel(
            f"[dim]Logs:[/dim] {log_dir}",
            title="[bold]codemonkeys review[/bold]",
            border_style="bright_blue",
        )
    )

    display.start()
    try:
        await engine.run(workflow, ctx)
    finally:
        display.stop()

    if getattr(args, "audit", False):
        import textwrap

        from rich.text import Text

        from codemonkeys.artifacts.schemas.audit import AgentAudit
        from codemonkeys.core.agents.agent_auditor import (
            AGENT_SOURCES,
            make_agent_auditor,
            run_audit_with_fixes,
        )
        from codemonkeys.core.log_metrics import extract_metrics
        from codemonkeys.core.runner import AgentRunner

        def _print_audit_event(event: dict) -> None:
            etype = event.get("type", "")
            if etype == "thinking":
                content = event.get("content", "")
                if not content:
                    return
                wrapped = textwrap.indent(content, "  ")
                console.print(Text("  thinking", style="dim italic"))
                console.print(Text(wrapped, style="dim"))
                console.print()
            elif etype == "tool_use":
                console.print(
                    f"  [bold cyan]{event.get('detail', event.get('name', '?'))}[/bold cyan]"
                )
                console.print()
            elif etype == "text":
                content = event.get("content", "")
                if content:
                    console.print("  [green]output[/green]")
                    console.print(textwrap.indent(content, "  "))
                    console.print()
            elif etype == "rate_limit_wait":
                wait = event.get("wait_seconds", "?")
                console.print(f"  [yellow]rate limited — waiting {wait}s[/yellow]")

        log_files = sorted(log_dir.glob("*.log"))
        if not log_files:
            console.print("[yellow]No log files found for audit[/yellow]")
        else:
            runner = AgentRunner(cwd=str(cwd), log_dir=log_dir)
            audit_schema = {
                "type": "json_schema",
                "schema": AgentAudit.model_json_schema(),
            }
            for lf in log_files:
                metrics = extract_metrics(lf)
                agent_base = metrics.agent_name.split("__")[0]
                source_path = AGENT_SOURCES.get(agent_base)
                if not source_path:
                    console.print(
                        f"  [dim]Skipping {metrics.agent_name} — no source mapping[/dim]"
                    )
                    continue
                auditor = make_agent_auditor(source_path)
                audit_model = auditor.model or "sonnet"
                console.print()
                console.print(
                    Panel(
                        f"[bold]agent_auditor[/bold]  model={audit_model}\n"
                        f"target: {agent_base}  source: {source_path}\n"
                        f"[dim]Logs: {log_dir}[/dim]",
                        title="[bold]codemonkeys audit[/bold]",
                        border_style="bright_blue",
                    )
                )
                audit_result = await runner.run_agent(
                    auditor,
                    metrics.to_json(),
                    output_format=audit_schema,
                    agent_name=f"audit__{agent_base}",
                    on_event=_print_audit_event,
                )
                if audit_result.structured:
                    await run_audit_with_fixes(
                        console,
                        runner,
                        audit_result.structured,
                        agent_base,
                        source_path,
                        log_metrics_json=metrics.to_json(),
                    )


def main() -> None:
    parser = argparse.ArgumentParser(description="codemonkeys review pipeline")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--files", nargs="+", help="Specific files to review")
    scope.add_argument(
        "--diff", action="store_true", help="Review changed files (git diff vs HEAD)"
    )
    scope.add_argument(
        "--repo", action="store_true", help="Review all .py files in the repo"
    )
    scope.add_argument(
        "--deep-clean",
        action="store_true",
        help="Deep clean — stabilize, write characterization tests, and refactor the codebase",
    )
    parser.add_argument(
        "--auto-fix", action="store_true", help="Fix all findings without triage"
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Generate an interactive HTML workflow graph after run",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run the agent auditor on all agent logs after the workflow completes",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
