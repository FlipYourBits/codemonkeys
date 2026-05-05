"""CLI review pipeline — discover, review, architecture, NLP triage, fix, verify.

Run from the project root:
    .venv/bin/python -m codemonkeys.run_review
    .venv/bin/python -m codemonkeys.run_review --files codemonkeys/core/runner.py codemonkeys/core/analysis.py
    .venv/bin/python -m codemonkeys.run_review --auto-fix
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from collections.abc import Callable
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings
from codemonkeys.artifacts.schemas.findings import (
    BatchFindings,
    FileFindings,
    Finding,
    FixRequest,
)
from codemonkeys.artifacts.schemas.results import FixResult
from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.core.analysis import analyze_files, format_analysis

console = Console()

# Log directory — created once per run
_log_dir: Path | None = None


def _init_log_dir(cwd: Path) -> Path:
    global _log_dir
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    _log_dir = cwd / ".codemonkeys" / "logs" / ts
    _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def _log_path(agent_name: str) -> Path:
    assert _log_dir is not None
    safe = agent_name.replace("/", "__").replace("\\", "__").replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return _log_dir / f"{safe}_{ts}.log"


def _serialize_block(block: Any) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ThinkingBlock):
        return {"type": "thinking", "thinking": block.thinking}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
        }
    if dataclasses.is_dataclass(block) and not isinstance(block, type):
        return {k: v for k, v in dataclasses.asdict(block).items() if v is not None}
    return {"raw": repr(block)}


def _serialize_message(msg: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"type": type(msg).__name__}

    if isinstance(msg, AssistantMessage):
        entry["model"] = msg.model
        entry["usage"] = msg.usage
        entry["stop_reason"] = msg.stop_reason
        entry["content"] = [_serialize_block(b) for b in msg.content]

    elif isinstance(msg, TaskStartedMessage):
        entry["task_id"] = msg.task_id
        entry["description"] = msg.description

    elif isinstance(msg, TaskProgressMessage):
        entry["task_id"] = msg.task_id
        entry["usage"] = dict(msg.usage) if msg.usage else None
        entry["last_tool_name"] = msg.last_tool_name

    elif isinstance(msg, TaskNotificationMessage):
        entry["task_id"] = msg.task_id
        entry["status"] = msg.status
        entry["summary"] = msg.summary
        entry["usage"] = dict(msg.usage) if msg.usage else None

    elif isinstance(msg, ResultMessage):
        entry["is_error"] = msg.is_error
        entry["duration_ms"] = msg.duration_ms
        entry["num_turns"] = msg.num_turns
        entry["total_cost_usd"] = msg.total_cost_usd
        entry["usage"] = msg.usage
        entry["result"] = msg.result
        entry["stop_reason"] = msg.stop_reason
        entry["errors"] = msg.errors

    elif isinstance(msg, UserMessage):
        entry["content"] = (
            msg.content
            if isinstance(msg.content, str)
            else [_serialize_block(b) for b in msg.content]
        )

    elif isinstance(msg, SystemMessage):
        entry["subtype"] = msg.subtype
        entry["data"] = msg.data

    else:
        entry["raw"] = repr(msg)

    return entry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SEV_STYLE = {
    "high": "bold red",
    "medium": "yellow",
    "low": "cyan",
    "info": "dim",
}


def _phase_header(name: str) -> None:
    console.print()
    console.rule(f"[bold]{name}[/bold]", style="bright_blue")
    console.print()


def _tool_detail(block: ToolUseBlock, cwd: str = "") -> str:
    name = block.name
    tool_input = block.input or {}
    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "?")
        if cwd and path.startswith(cwd):
            path = path[len(cwd) :].lstrip("/")
        return f"{name}({path})"
    if name == "Grep":
        return f"Grep('{tool_input.get('pattern', '?')}')"
    if name == "Glob":
        return f"Glob({tool_input.get('pattern', tool_input.get('path', '?'))})"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:80]})" if cmd else "Bash"
    if name == "StructuredOutput":
        return "StructuredOutput()"
    return name


def _render_agent_card(s: dict[str, Any]) -> Text:
    """Build a multi-line card for one agent in a Live display."""
    card = Text()

    if s["status"] == "waiting":
        card.append("  ○ ", style="dim")
        card.append(s["agent_name"], style="dim")
        card.append(f"  {s['model']}", style="dim")
        card.append("  waiting", style="dim")
    elif s["status"] == "running":
        card.append("  ● ", style="yellow")
        card.append(s["agent_name"], style="bold")
        card.append(f"  {s['model']}", style="dim")
        card.append("  running", style="yellow")
        if s["tokens"]:
            card.append(f"  {s['tokens']:,} tok", style="dim")
    elif s["status"] == "error":
        card.append("  ● ", style="bold red")
        card.append(s["agent_name"], style="bold")
        card.append(f"  {s['model']}", style="dim")
        card.append("  error", style="bold red")
        if s["tokens"]:
            card.append(f"  {s['tokens']:,} tok", style="dim")
    else:
        card.append("  ● ", style="green")
        card.append(s["agent_name"], style="bold")
        card.append(f"  {s['model']}", style="dim")
        card.append("  done", style="green")
        if s["tokens"]:
            card.append(f"  {s['tokens']:,} tok", style="dim")
        if s["cost"]:
            card.append(f"  {s['cost']}", style="dim")

    card.append("\n")
    card.append(f"    {s['files_label']}\n", style="cyan")

    if s["status"] == "running" and s["activity"]:
        card.append(f"    {s['activity']}\n", style="dim")
    elif s["status"] == "done":
        n = s["findings"]
        n_style = "green" if n == 0 else "yellow"
        card.append(f"    {n} finding{'s' if n != 1 else ''}\n", style=n_style)
    elif s["status"] == "error" and s["activity"]:
        card.append(f"    {s['activity']}\n", style="red")

    return card


def _format_cost(result: ResultMessage) -> str:
    cost = getattr(result, "total_cost_usd", None)
    return f"${cost:.2f}" if cost else ""


def _format_result(result: ResultMessage) -> str:
    usage = result.usage or {}
    output_tok = usage.get("output_tokens", 0)
    return f"{output_tok:,} out  {_format_cost(result)}"


async def _run_agent(
    agent: AgentDefinition,
    prompt: str,
    cwd: str,
    output_schema: dict[str, Any] | None = None,
    *,
    log_name: str = "agent",
    on_event: Callable[[str, str, int], None] | None = None,
) -> ResultMessage | None:
    """Run an agent via query() and return the ResultMessage.

    If *on_event* is set, call ``on_event(event, detail, tokens)`` instead
    of printing directly.  *event* is ``"tool"`` or ``"done"``.
    *tokens* is the running cumulative ``input_tokens + output_tokens``.
    """
    options = ClaudeAgentOptions(
        system_prompt=agent.prompt,
        model=agent.model or "sonnet",
        cwd=cwd,
        permission_mode=agent.permissionMode or "dontAsk",
        allowed_tools=agent.tools or [],
        disallowed_tools=agent.disallowedTools or [],
        output_format=output_schema,
        plugins=[],
        setting_sources=[],
    )

    log_file = _log_path(log_name)
    last_result: ResultMessage | None = None
    cumulative_tokens = 0
    last_counted_id: str | None = None

    def _log(entry: dict[str, Any]) -> None:
        entry["ts"] = datetime.now(timezone.utc).isoformat()
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, default=repr) + "\n")

    _log(
        {
            "event": "agent_start",
            "name": log_name,
            "description": agent.description,
            "model": agent.model,
            "tools": agent.tools,
            "prompt_length": len(agent.prompt),
            "user_prompt": prompt,
        }
    )

    async def _prompt_gen():
        yield {"type": "user", "message": {"role": "user", "content": prompt}}

    async for message in query(prompt=_prompt_gen(), options=options):
        _log(_serialize_message(message))

        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.id != last_counted_id:
                        last_counted_id = block.id
                        usage = message.usage or {}
                        cumulative_tokens += usage.get("input_tokens", 0) + usage.get(
                            "output_tokens", 0
                        )
                    detail = _tool_detail(block, cwd)
                    if on_event:
                        on_event("tool", detail, cumulative_tokens)
                    else:
                        console.print(
                            f"    [dim]{detail}[/dim]  "
                            f"[dim]{cumulative_tokens:,} tok[/dim]"
                        )

        elif isinstance(message, ResultMessage):
            last_result = message
            usage = message.usage or {}
            cumulative_tokens = usage.get("input_tokens", 0) + usage.get(
                "output_tokens", 0
            )
            if on_event:
                on_event("done", _format_cost(message), cumulative_tokens)
            else:
                console.print(
                    f"    [green]done[/green]  [dim]{_format_result(message)}[/dim]"
                )

    # Write debug graph: system prompt + user prompt + structured output
    debug_path = log_file.with_suffix(".md")
    structured_out = ""
    if last_result:
        raw = getattr(last_result, "structured_output", None)
        if raw:
            if isinstance(raw, str):
                try:
                    structured_out = json.dumps(json.loads(raw), indent=2)
                except json.JSONDecodeError:
                    structured_out = raw
            else:
                structured_out = json.dumps(raw, indent=2, default=repr)
        elif getattr(last_result, "result", None):
            structured_out = last_result.result

    with open(debug_path, "w") as f:
        f.write(f"# Agent: {log_name}\n\n")
        f.write(f"**Model:** {agent.model or 'sonnet'}\n")
        f.write(f"**Tools:** {', '.join(agent.tools or [])}\n\n")
        f.write("## System Prompt\n\n```\n")
        f.write(agent.prompt)
        f.write("\n```\n\n## User Prompt\n\n```\n")
        f.write(prompt)
        f.write("\n```\n\n## Structured Output\n\n```json\n")
        f.write(structured_out or "(no output)")
        f.write("\n```\n")

    return last_result


def _parse_result(result: ResultMessage | None, model_cls: type, fallback: Any) -> Any:
    """Extract structured output from a ResultMessage."""
    if result is None:
        return fallback

    structured = getattr(result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        return model_cls.model_validate(structured)

    raw = getattr(result, "result", "") or ""
    try:
        return model_cls.model_validate_json(raw)
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Pipeline phases
# ---------------------------------------------------------------------------


def _find_diff_files(cwd: Path) -> list[str]:
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        return [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
    return []


def _find_all_files(cwd: Path) -> list[str]:
    excluded = ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
    return sorted(
        str(p.relative_to(cwd))
        for p in cwd.rglob("*.py")
        if not any(part in p.parts for part in excluded)
    )


def discover(
    cwd: Path, mode: str, explicit_files: list[str] | None = None
) -> dict[str, Any]:
    """Find files and run static analysis."""
    _phase_header("Discover")

    if explicit_files:
        files = explicit_files
        console.print(f"  Mode: [bold]explicit[/bold] ({len(files)} files)")
    elif mode == "diff":
        files = _find_diff_files(cwd)
        console.print("  Mode: [bold]git diff[/bold] (changed files vs HEAD)")
    else:
        files = _find_all_files(cwd)
        console.print("  Mode: [bold]full repo[/bold] (all .py files)")

    if not files:
        console.print("  [yellow]No Python files found.[/yellow]")
        return {"files": [], "structural_metadata": ""}

    console.print(f"  [bold]{len(files)}[/bold] files in scope")
    for f in files:
        console.print(f"    [dim]{f}[/dim]")

    analyses = analyze_files(files, root=cwd)
    metadata = format_analysis(analyses)
    console.print(f"  Structural metadata: [bold]{len(metadata):,}[/bold] chars")

    return {"files": files, "structural_metadata": metadata}


def _is_test_file(path: str) -> bool:
    parts = Path(path).parts
    return Path(path).name.startswith("test_") or "tests" in parts


def _make_batches(files: list[str], max_size: int = 3) -> list[list[str]]:
    if not files:
        return []
    n_batches = math.ceil(len(files) / max_size)
    base, extra = divmod(len(files), n_batches)
    batches: list[list[str]] = []
    i = 0
    for b in range(n_batches):
        size = base + (1 if b < extra else 0)
        batches.append(files[i : i + size])
        i += size
    return batches


async def review(
    files: list[str], cwd: str, *, max_concurrent: int = 5
) -> list[FileFindings]:
    """Run reviewer agents in parallel, batching up to 3 files per agent."""
    _phase_header("Per-File Review")

    test_files = [f for f in files if _is_test_file(f)]
    prod_files = [f for f in files if not _is_test_file(f)]

    batches: list[tuple[list[str], str]] = [
        (b, "haiku") for b in _make_batches(test_files)
    ] + [(b, "sonnet") for b in _make_batches(prod_files)]

    sem = asyncio.Semaphore(max_concurrent)

    agent_state: dict[int, dict[str, Any]] = {}
    for i, (bf, model) in enumerate(batches):
        agent_state[i] = {
            "agent_name": "file_reviewer",
            "model": model,
            "files": bf,
            "files_label": ", ".join(bf),
            "status": "waiting",
            "activity": "",
            "tokens": 0,
            "findings": 0,
            "cost": "",
        }

    def _render() -> Group:
        return Group(*[_render_agent_card(s) for s in agent_state.values()])

    all_findings: dict[str, FileFindings] = {}

    async def _review_batch(batch_idx: int, live: Live) -> list[FileFindings]:
        st = agent_state[batch_idx]
        batch_files = st["files"]
        model = st["model"]

        async with sem:
            st["status"] = "running"
            st["activity"] = "starting..."
            live.update(_render())

            def on_event(event: str, detail: str, tokens: int) -> None:
                st["tokens"] = tokens
                if event == "tool":
                    st["activity"] = detail
                live.update(_render())

            try:
                agent = make_python_file_reviewer(batch_files, model=model)
                output_schema = {
                    "type": "json_schema",
                    "schema": BatchFindings.model_json_schema(),
                }
                result = await _run_agent(
                    agent,
                    f"Review: {', '.join(batch_files)}",
                    cwd,
                    output_schema,
                    log_name=f"review_batch__{batch_files[0]}",
                    on_event=on_event,
                )
                batch_result = _parse_result(
                    result,
                    BatchFindings,
                    BatchFindings(
                        results=[
                            FileFindings(
                                file=f,
                                summary="Could not parse output",
                                findings=[],
                            )
                            for f in batch_files
                        ]
                    ),
                )

                cost = getattr(result, "total_cost_usd", 0) or 0
                st["cost"] = f"${cost:.2f}" if cost else ""

                usage = (result.usage or {}) if result else {}
                st["tokens"] = usage.get("input_tokens", 0) + usage.get(
                    "output_tokens", 0
                )

                results_by_file = {r.file: r for r in batch_result.results}
                found: list[FileFindings] = []
                total_findings = 0
                for f in batch_files:
                    ff = results_by_file.get(
                        f,
                        FileFindings(
                            file=f, summary="Missing from results", findings=[]
                        ),
                    )
                    total_findings += len(ff.findings)
                    all_findings[f] = ff
                    found.append(ff)
                st["status"] = "done"
                st["findings"] = total_findings
                return found
            except Exception as exc:
                results: list[FileFindings] = []
                for f in batch_files:
                    ff = FileFindings(
                        file=f, summary=f"Agent failed: {exc}", findings=[]
                    )
                    all_findings[f] = ff
                    results.append(ff)
                st["status"] = "error"
                st["activity"] = str(exc)[:60]
                return results
            finally:
                live.update(_render())

    with Live(_render(), console=console, refresh_per_second=4) as live:
        await asyncio.gather(*[_review_batch(i, live) for i in agent_state])

    return [all_findings[f] for f in files]


async def architecture_review(
    files: list[str],
    file_summaries: list[dict[str, str]],
    structural_metadata: str,
    cwd: str,
) -> ArchitectureFindings:
    """Run the architecture reviewer agent."""
    _phase_header("Architecture Review")

    agent = make_architecture_reviewer(
        files=files,
        file_summaries=file_summaries,
        structural_metadata=structural_metadata,
    )
    output_schema = {
        "type": "json_schema",
        "schema": ArchitectureFindings.model_json_schema(),
    }

    state: dict[str, Any] = {
        "agent_name": "architecture_reviewer",
        "model": "opus",
        "files_label": ", ".join(files),
        "status": "running",
        "activity": "starting...",
        "tokens": 0,
        "cost": "",
        "findings": 0,
    }

    def _render_arch() -> Group:
        return Group(_render_agent_card(state))

    def on_event(event: str, detail: str, tokens: int) -> None:
        state["tokens"] = tokens
        if event == "tool":
            state["activity"] = detail
        live.update(_render_arch())

    with Live(_render_arch(), console=console, refresh_per_second=4) as live:
        try:
            result = await _run_agent(
                agent,
                "Review the codebase for cross-file design issues.",
                cwd,
                output_schema,
                log_name="architecture_review",
                on_event=on_event,
            )
            findings = _parse_result(
                result,
                ArchitectureFindings,
                ArchitectureFindings(files_reviewed=files, findings=[]),
            )
            cost = getattr(result, "total_cost_usd", 0) or 0
            state["cost"] = f"${cost:.2f}" if cost else ""
            usage = (result.usage or {}) if result else {}
            state["tokens"] = usage.get("input_tokens", 0) + usage.get(
                "output_tokens", 0
            )
            state["status"] = "done"
            state["findings"] = len(findings.findings)
        except Exception as exc:
            findings = ArchitectureFindings(files_reviewed=files, findings=[])
            state["status"] = "error"
            state["activity"] = str(exc)[:60]
        live.update(_render_arch())

    return findings


_SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def present_findings(
    per_file: list[FileFindings],
    arch: ArchitectureFindings,
) -> list[Finding]:
    """Print all findings sorted by severity and return a flat list for triage."""
    _phase_header("Findings")

    all_findings: list[Finding] = []

    for ff in per_file:
        for f in ff.findings:
            f.source = "file_reviewer"
        all_findings.extend(ff.findings)

    for af in arch.findings:
        all_findings.append(
            Finding(
                file=", ".join(af.files),
                line=None,
                severity=af.severity,
                category="quality",
                subcategory=af.subcategory,
                title=af.title,
                description=af.description,
                suggestion=af.suggestion,
                source="architecture_reviewer",
            )
        )

    if not all_findings:
        console.print("  [bold green]No findings! Codebase looks clean.[/bold green]")
        return all_findings

    all_findings.sort(key=lambda f: _SEV_ORDER.get(f.severity, 99))

    for idx, f in enumerate(all_findings, 1):
        sev_style = _SEV_STYLE.get(f.severity, "")
        loc = f"{f.file}:{f.line}" if f.line else f.file
        console.print(
            f"  [dim]{idx:>3}.[/dim] [{sev_style}]{f.severity.upper():<6}[/{sev_style}] "
            f"[cyan]{loc}[/cyan]  [dim]({f.source})[/dim]"
        )
        console.print(f"       {f.title}")
        if f.description:
            console.print(f"       [dim]{f.description}[/dim]")
        if f.suggestion:
            console.print(f"       [green]Fix:[/green] {f.suggestion}")
        console.print()

    console.print(f"  [bold]{len(all_findings)}[/bold] total finding(s)")

    return all_findings


async def nlp_triage(
    all_findings: list[Finding],
    per_file: list[FileFindings],
    cwd: str,
) -> list[FixRequest]:
    """Let the user describe what to fix in natural language, then translate to FixRequests."""
    _phase_header("Triage")

    if not all_findings:
        return []

    findings_summary = json.dumps(
        [{"idx": i + 1, **f.model_dump()} for i, f in enumerate(all_findings)],
        indent=2,
    )

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
    if not user_input or user_input.lower() == "skip":
        console.print("  [dim]Skipping fixes.[/dim]")
        return []

    triage_prompt = f"""\
Here are the code review findings:

{findings_summary}

The user said: "{user_input}"

Based on the user's instruction, return a JSON array of objects, each with:
- "file": the file path
- "finding_indices": array of 1-based finding indices to fix in that file

Group findings by file. Only include findings the user wants to fix.
Return ONLY the JSON array, no explanation."""

    agent = AgentDefinition(
        description="Triage filter",
        prompt="You translate natural language triage instructions into structured selections. Return only valid JSON.",
        model="haiku",
        tools=[],
        permissionMode="dontAsk",
    )

    console.print()
    result = await _run_agent(agent, triage_prompt, cwd, log_name="triage")
    raw = getattr(result, "result", "") or "" if result else ""

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        selections = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        console.print(
            "  [yellow]Could not parse triage response, fixing all findings.[/yellow]"
        )
        selections = None

    if selections is None:
        fix_requests = []
        for ff in per_file:
            if ff.findings:
                fix_requests.append(FixRequest(file=ff.file, findings=ff.findings))
        return fix_requests

    fix_requests = []
    for sel in selections:
        file_path = sel["file"]
        indices = sel.get("finding_indices", [])
        matched = [all_findings[i - 1] for i in indices if 1 <= i <= len(all_findings)]
        if matched:
            fix_requests.append(FixRequest(file=file_path, findings=matched))

    console.print(
        f"\n  Selected [bold]{sum(len(fr.findings) for fr in fix_requests)}[/bold] finding(s) to fix:"
    )
    for fr in fix_requests:
        console.print(f"    [cyan]{fr.file}[/cyan]: {len(fr.findings)} finding(s)")

    confirm = console.input("\n  Proceed? [bold]\\[Y/n][/bold] ").strip().lower()
    if confirm and confirm != "y":
        console.print("  [dim]Aborted.[/dim]")
        return []

    return fix_requests


async def fix(fix_requests: list[FixRequest], cwd: str) -> list[FixResult]:
    """Run fixer agents for selected findings."""
    _phase_header("Fix")

    if not fix_requests:
        console.print("  [dim]Nothing to fix.[/dim]")
        return []

    results: list[FixResult] = []
    for i, req in enumerate(fix_requests, 1):
        console.print(f"  [{i}/{len(fix_requests)}] [cyan]{req.file}[/cyan]")
        findings_json = req.model_dump_json(indent=2)
        agent = make_python_code_fixer(req.file, findings_json)
        output_schema = {
            "type": "json_schema",
            "schema": FixResult.model_json_schema(),
        }
        result_msg = await _run_agent(
            agent,
            f"Fix findings in {req.file}",
            cwd,
            output_schema,
            log_name=f"fix__{req.file}",
        )
        result = _parse_result(
            result_msg,
            FixResult,
            FixResult(
                file=req.file, fixed=[], skipped=["Could not parse agent output"]
            ),
        )
        fixed_str = f"[green]{len(result.fixed)} fixed[/green]"
        skipped_str = (
            f"[yellow]{len(result.skipped)} skipped[/yellow]"
            if result.skipped
            else f"[dim]{len(result.skipped)} skipped[/dim]"
        )
        console.print(f"  Result: {fixed_str}, {skipped_str}")
        results.append(result)

    return results


def verify(cwd: Path) -> None:
    """Run mechanical checks."""
    import subprocess

    _phase_header("Verify")
    python = sys.executable

    for name, cmd in [
        ("pytest", [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"]),
        ("ruff", [python, "-m", "ruff", "check", "."]),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if r.returncode == 0:
            console.print(f"  {name}: [bold green]PASS[/bold green]")
        else:
            console.print(f"  {name}: [bold red]FAIL[/bold red]")
            for line in r.stdout.strip().splitlines()[:10]:
                console.print(f"    [dim]{line}[/dim]")


def report(
    per_file: list[FileFindings],
    arch: ArchitectureFindings,
    fix_results: list[FixResult],
) -> None:
    """Print summary."""
    _phase_header("Report")
    total_findings = sum(len(ff.findings) for ff in per_file) + len(arch.findings)
    total_fixed = sum(len(r.fixed) for r in fix_results)
    total_skipped = sum(len(r.skipped) for r in fix_results)

    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Label", style="bold")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Findings", str(total_findings))
    summary_table.add_row("Fixed", f"[green]{total_fixed}[/green]")
    summary_table.add_row(
        "Skipped",
        f"[yellow]{total_skipped}[/yellow]" if total_skipped else str(total_skipped),
    )
    console.print(Panel(summary_table, title="Summary", border_style="bright_blue"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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


async def main_async(args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    log_dir = _init_log_dir(cwd)

    console.print(
        Panel(
            f"[dim]Logs:[/dim] {log_dir}",
            title="[bold]codemonkeys review[/bold]",
            border_style="bright_blue",
        )
    )

    # 1. Discover
    if args.files:
        mode = "explicit"
    elif args.diff:
        mode = "diff"
    elif args.repo:
        mode = "repo"
    else:
        mode = _select_mode()

    disc = discover(cwd, mode=mode, explicit_files=args.files or None)
    files = disc["files"]
    metadata = disc["structural_metadata"]

    if not files:
        return

    # 2. Per-file review
    per_file = await review(files, str(cwd))

    # 3. Architecture review
    summaries = [{"file": ff.file, "summary": ff.summary} for ff in per_file]
    arch = await architecture_review(files, summaries, metadata, str(cwd))

    # 4. Present findings
    all_findings = present_findings(per_file, arch)

    # 5. Triage
    if args.auto_fix:
        fix_requests = []
        for ff in per_file:
            if ff.findings:
                fix_requests.append(FixRequest(file=ff.file, findings=ff.findings))
    else:
        fix_requests = await nlp_triage(all_findings, per_file, str(cwd))

    if not fix_requests:
        _phase_header("Done")
        console.print(
            f"  [bold]{len(all_findings)}[/bold] finding(s) reported, no fixes requested."
        )
        return

    # 6. Fix
    fix_results = await fix(fix_requests, str(cwd))

    # 7. Verify
    if fix_results:
        verify(cwd)

    # 8. Report
    report(per_file, arch, fix_results)


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
    parser.add_argument(
        "--auto-fix", action="store_true", help="Fix all findings without triage"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
