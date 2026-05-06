"""Run a single agent independently for testing and debugging.

Usage:
    uv run python -m codemonkeys.run_agent python_file_reviewer --files src/main.py
    uv run python -m codemonkeys.run_agent changelog_reviewer
    uv run python -m codemonkeys.run_agent readme_reviewer
    uv run python -m codemonkeys.run_agent python_implementer --prompt-file plan.md
    uv run python -m codemonkeys.run_agent python_code_fixer --files src/main.py --prompt-file findings.json
    uv run python -m codemonkeys.run_agent architecture_reviewer --files src/a.py src/b.py
    uv run python -m codemonkeys.run_agent python_characterization_tester --files src/main.py
    uv run python -m codemonkeys.run_agent python_structural_refactorer --files src/a.py \\
        --prompt "Break circular dep between a.py and b.py" --refactor-type circular_deps

Logs are written to .codemonkeys/logs/<timestamp>/:
  - .log  — raw JSONL of every SDK event (tools called, token usage per turn)
  - .md   — readable: system prompt, user prompt, structured output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from codemonkeys.core.runner import AgentRunner

console = Console()

AGENT_NAMES = [
    "python_file_reviewer",
    "changelog_reviewer",
    "readme_reviewer",
    "python_implementer",
    "python_code_fixer",
    "architecture_reviewer",
    "python_characterization_tester",
    "python_structural_refactorer",
    "spec_compliance_reviewer",
    "agent_auditor",
]


def _init_log_dir(cwd: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = cwd / ".codemonkeys" / "logs" / ts
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _read_prompt(args: argparse.Namespace) -> str | None:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text()
    return None


def _build_python_file_reviewer(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.findings import FileFindings
    from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer

    agent = make_python_file_reviewer(
        files,
        model=args.model or "sonnet",
        resilience=args.resilience,
        test_quality=args.test_quality,
    )
    prompt = _read_prompt(args) or f"Review: {', '.join(files)}"
    schema = {"type": "json_schema", "schema": FileFindings.model_json_schema()}
    return agent, prompt, schema


def _build_changelog_reviewer(
    args: argparse.Namespace,
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.findings import FileFindings
    from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer

    agent = make_changelog_reviewer()
    prompt = (
        _read_prompt(args) or "Review CHANGELOG.md for accuracy against git history."
    )
    schema = {"type": "json_schema", "schema": FileFindings.model_json_schema()}
    return agent, prompt, schema


def _build_readme_reviewer(
    args: argparse.Namespace,
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.findings import FileFindings
    from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer

    agent = make_readme_reviewer()
    prompt = _read_prompt(args) or "Review README.md for accuracy against the codebase."
    schema = {"type": "json_schema", "schema": FileFindings.model_json_schema()}
    return agent, prompt, schema


def _build_python_implementer(
    args: argparse.Namespace,
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.core.agents.python_implementer import make_python_implementer

    agent = make_python_implementer()
    prompt = _read_prompt(args)
    if not prompt:
        console.print(
            "[red]python_implementer requires --prompt or --prompt-file with the plan[/red]"
        )
        sys.exit(1)
    return agent, prompt, None


def _build_python_code_fixer(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer

    if len(files) != 1:
        console.print(
            "[red]python_code_fixer requires exactly one --files argument[/red]"
        )
        sys.exit(1)
    findings_json = _read_prompt(args)
    if not findings_json:
        console.print(
            "[red]python_code_fixer requires --prompt or --prompt-file with findings JSON[/red]"
        )
        sys.exit(1)
    agent = make_python_code_fixer(files[0], findings_json)
    return agent, f"Fix the findings in {files[0]}.", None


def _build_architecture_reviewer(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings
    from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
    from codemonkeys.core.analysis import analyze_files, format_analysis

    cwd = Path.cwd()
    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)
    agent = make_architecture_reviewer(
        files=files,
        file_summaries=[
            {"file": f, "summary": "(standalone run — no summaries)"} for f in files
        ],
        structural_metadata=structural_metadata,
    )
    prompt = _read_prompt(args) or "Review the codebase for cross-file design issues."
    schema = {"type": "json_schema", "schema": ArchitectureFindings.model_json_schema()}
    return agent, prompt, schema


def _build_python_characterization_tester(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.refactor import CharTestResult
    from codemonkeys.core.agents.python_characterization_tester import (
        make_python_characterization_tester,
    )

    agent = make_python_characterization_tester(
        files=files,
        import_context="",
        uncovered_lines={f: [] for f in files},
    )
    prompt = (
        _read_prompt(args) or f"Write characterization tests for: {', '.join(files)}"
    )
    schema = {"type": "json_schema", "schema": CharTestResult.model_json_schema()}
    return agent, prompt, schema


def _build_python_structural_refactorer(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.core.agents.python_structural_refactorer import (
        make_python_structural_refactorer,
    )

    problem = _read_prompt(args)
    if not problem:
        console.print(
            "[red]python_structural_refactorer requires --prompt or --prompt-file "
            "describing the problem[/red]"
        )
        sys.exit(1)
    refactor_type = args.refactor_type or "circular_deps"
    agent = make_python_structural_refactorer(
        files=files,
        problem_description=problem,
        refactor_type=refactor_type,
        test_files=[],
    )
    return agent, f"Refactor ({refactor_type}): {', '.join(files)}", None


def _build_spec_compliance_reviewer(
    files: list[str], args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
    from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings
    from codemonkeys.core.agents.spec_compliance_reviewer import (
        make_spec_compliance_reviewer,
    )

    prompt_text = _read_prompt(args)
    if not prompt_text:
        console.print(
            "[red]spec_compliance_reviewer requires --prompt-file with a JSON spec[/red]\n"
            '[dim]Format: {"title": "...", "description": "...", "steps": [{"description": "...", "files": [...]}]}[/dim]'
        )
        sys.exit(1)
    try:
        spec_data = json.loads(prompt_text)
        spec = FeaturePlan(
            title=spec_data["title"],
            description=spec_data.get("description", ""),
            steps=[PlanStep(**s) for s in spec_data.get("steps", [])],
        )
    except (json.JSONDecodeError, KeyError) as exc:
        console.print(f"[red]Failed to parse spec JSON: {exc}[/red]")
        sys.exit(1)
    agent = make_spec_compliance_reviewer(spec=spec, files=files, unplanned_files=[])
    schema = {
        "type": "json_schema",
        "schema": SpecComplianceFindings.model_json_schema(),
    }
    return agent, f"Review implementation against spec: {spec.title}", schema


def _build_agent_auditor(
    args: argparse.Namespace,
) -> tuple[Any, str, dict[str, Any] | None]:
    from codemonkeys.artifacts.schemas.audit import AgentAudit
    from codemonkeys.core.agents.agent_auditor import make_agent_auditor

    source_path = args.agent_source
    if not source_path:
        console.print("[red]agent_auditor requires --agent-source[/red]")
        sys.exit(1)
    prompt_text = _read_prompt(args)
    if not prompt_text:
        console.print(
            "[red]agent_auditor requires --prompt or --prompt-file with LogMetrics JSON[/red]"
        )
        sys.exit(1)
    agent = make_agent_auditor(source_path)
    schema = {"type": "json_schema", "schema": AgentAudit.model_json_schema()}
    return agent, prompt_text, schema


def _build_agent(
    name: str, args: argparse.Namespace
) -> tuple[Any, str, dict[str, Any] | None]:
    """Build an AgentDefinition, user prompt, and optional output schema from CLI args."""
    files = args.files or []

    needs_files = {
        "python_file_reviewer",
        "python_code_fixer",
        "architecture_reviewer",
        "python_characterization_tester",
        "python_structural_refactorer",
        "spec_compliance_reviewer",
    }
    if name in needs_files and not files:
        console.print(f"[red]{name} requires --files[/red]")
        sys.exit(1)

    builders = {
        "python_file_reviewer": lambda: _build_python_file_reviewer(files, args),
        "changelog_reviewer": lambda: _build_changelog_reviewer(args),
        "readme_reviewer": lambda: _build_readme_reviewer(args),
        "python_implementer": lambda: _build_python_implementer(args),
        "python_code_fixer": lambda: _build_python_code_fixer(files, args),
        "architecture_reviewer": lambda: _build_architecture_reviewer(files, args),
        "python_characterization_tester": lambda: _build_python_characterization_tester(
            files, args
        ),
        "python_structural_refactorer": lambda: _build_python_structural_refactorer(
            files, args
        ),
        "spec_compliance_reviewer": lambda: _build_spec_compliance_reviewer(
            files, args
        ),
        "agent_auditor": lambda: _build_agent_auditor(args),
    }
    return builders[name]()


async def main_async(args: argparse.Namespace) -> None:
    name = args.agent
    cwd = Path.cwd()
    log_dir = _init_log_dir(cwd)

    agent, prompt, output_format = _build_agent(name, args)

    if args.model:
        agent.model = args.model

    files_label = ", ".join(args.files) if args.files else ""
    model = agent.model or "sonnet"
    console.print(
        Panel(
            f"[bold]{name}[/bold]  model={model}\n"
            + (f"files: {files_label}\n" if files_label else "")
            + f"[dim]Logs: {log_dir}[/dim]",
            title="[bold]codemonkeys run_agent[/bold]",
            border_style="bright_blue",
        )
    )

    status = console.status("[dim]Starting agent...[/dim]", spinner="dots")
    tool_lines: list[str] = []

    def _on_tool(index: int, detail: str, tokens: int, cost: float) -> None:
        tool_lines.append(
            f"  [dim]#{index}[/dim] {detail}  [dim]({tokens:,} tok, ${cost:.4f})[/dim]"
        )
        status.update(
            "\n".join(tool_lines)
            + f"\n  [bold cyan]⠿ waiting...[/bold cyan]  [dim]({tokens:,} tok, ${cost:.4f})[/dim]"
        )

    runner = AgentRunner(cwd=str(cwd), log_dir=log_dir)
    status.start()
    try:
        result = await runner.run_agent(
            agent,
            prompt,
            output_format=output_format,
            agent_name=name,
            files=files_label,
            on_tool_call=_on_tool,
        )
    finally:
        status.stop()

    for line in tool_lines:
        console.print(line)

    console.print()
    if result.structured:
        console.print(
            Panel(json.dumps(result.structured, indent=2), title="Structured Output")
        )
    elif result.text:
        console.print(Panel(result.text[:2000], title="Text Output"))
    else:
        console.print("[yellow]No output returned[/yellow]")

    console.print(
        f"\n[dim]Duration:[/dim] {result.duration_ms / 1000:.1f}s  "
        f"[dim]Cost:[/dim] ${result.cost or 0:.4f}  "
        f"[dim]Usage:[/dim] {result.usage}"
    )
    console.print(f"[dim]Logs:[/dim] {log_dir}/")

    if getattr(args, "audit", False) and args.agent != "agent_auditor":
        console.print("\n[bold]Running agent audit...[/bold]")
        from codemonkeys.artifacts.schemas.audit import AgentAudit
        from codemonkeys.core.agents.agent_auditor import (
            AGENT_SOURCES,
            make_agent_auditor,
            run_audit_with_fixes,
        )
        from codemonkeys.core.log_metrics import extract_metrics

        log_files = sorted(log_dir.glob("*.log"))
        if log_files:
            metrics = extract_metrics(log_files[0])
            source_path = AGENT_SOURCES.get(name)
            if source_path:
                auditor = make_agent_auditor(source_path)
                audit_schema = {
                    "type": "json_schema",
                    "schema": AgentAudit.model_json_schema(),
                }
                audit_result = await runner.run_agent(
                    auditor,
                    metrics.to_json(),
                    output_format=audit_schema,
                    agent_name="agent_auditor",
                )
                if audit_result.structured:
                    await run_audit_with_fixes(
                        console, runner, audit_result.structured, name, source_path
                    )
                else:
                    console.print(
                        "[yellow]Audit produced no structured output[/yellow]"
                    )
            else:
                console.print(
                    f"[yellow]No source mapping for agent '{name}' — skipping audit[/yellow]"
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single codemonkeys agent for testing and debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s python_file_reviewer --files codemonkeys/core/runner.py
  %(prog)s changelog_reviewer
  %(prog)s changelog_reviewer --audit""",
    )
    parser.add_argument("agent", choices=AGENT_NAMES, help="Agent to run")
    parser.add_argument("--files", nargs="+", help="Files to pass to the agent")
    parser.add_argument("--prompt", help="User prompt text")
    parser.add_argument("--prompt-file", help="Read user prompt from a file")
    parser.add_argument("--model", help="Override the agent's default model")
    parser.add_argument(
        "--resilience",
        action="store_true",
        help="(file_reviewer) Enable resilience checklist",
    )
    parser.add_argument(
        "--test-quality",
        action="store_true",
        help="(file_reviewer) Enable test quality checklist",
    )
    parser.add_argument(
        "--refactor-type",
        choices=[
            "circular_deps",
            "layering",
            "god_modules",
            "extract_shared",
            "dead_code",
            "naming",
        ],
        help="(structural_refactorer) Type of refactoring",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run the agent auditor on this agent's logs after completion",
    )
    parser.add_argument(
        "--agent-source", help="(agent_auditor) Path to the agent source .py file"
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
