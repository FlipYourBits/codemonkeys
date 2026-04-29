"""Multiagent code review using Claude Agent SDK's built-in agent dispatch.

The coordinator dispatches a code reviewer and a test runner (read-only),
presents findings, then optionally dispatches a fixer agent with write perms.

Usage:
    .venv/bin/python examples/multiagent_review.py /path/to/repo
    .venv/bin/python examples/multiagent_review.py .
    .venv/bin/python examples/multiagent_review.py . --no-fix
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    ToolUseBlock,
    query,
)

from agentpipe.skills.python import CLEAN_CODE as PYTHON_CLEAN_CODE


# ── Output models ────────────────────────────────────────────────


class Finding(BaseModel):
    file: str = Field(description="File path relative to repo root")
    line: int = Field(description="Line number")
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Issue severity")
    source: Literal["code_review", "test_runner"] = Field(description="Which agent found this")
    category: str = Field(description="e.g. logic_error, test_failure, resource_leak")
    description: str = Field(description="What the issue is")
    recommendation: str = Field(description="How to fix it")


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(description="Brief overall assessment")
    tests_passed: bool = Field(description="Whether all tests passed")


# ── Agent definitions ────────────────────────────────────────────

COORDINATOR_PROMPT = """\
You are a code quality coordinator. You have exactly two review agents:

1. "code_reviewer" — static code review (logic errors, leaks, dead code)
2. "test_runner" — runs pytest and analyzes failures

Your job:
1. Dispatch BOTH agents by name. Always dispatch both, never skip one.
2. Wait for their results.
3. Combine ALL findings into the structured output format.

Include every finding from every agent — do not summarize or drop any.

If a fixer agent is available and you are asked to fix issues, dispatch it
with the specific findings to fix."""


CODE_REVIEWER = AgentDefinition(
    description="Reviews Python code for logic errors, resource leaks, error handling gaps, dead code.",
    prompt="""\
Review the Python code in this repository for:
- Logic errors and off-by-one bugs
- Resource leaks (unclosed files, connections)
- Error handling gaps (bare except, swallowed errors)
- Dead code and unused imports
- Concurrency issues

Only review .py files. Ignore all other file types.

Focus on the diff from the main branch if available (git diff main...HEAD -- '*.py').
If no diff, review the most recently changed .py files.

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW), description.""",
    model="claude-haiku-4-5-20251001",
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Edit", "Write", "Bash(git push*)", "Bash(git commit*)"],
    permissionMode="bypassPermissions",
)


TEST_RUNNER = AgentDefinition(
    description="Runs pytest and analyzes test failures to identify root causes.",
    prompt="""\
Run the test suite and analyze any failures:

1. Run: python -m pytest -x -q --tb=short --no-header
2. For each failure, read the failing test and code under test
3. Identify the root cause
4. Report: file, line, severity (HIGH/MEDIUM/LOW), description, recommended fix

If all tests pass, report that clearly.""",
    model="claude-haiku-4-5-20251001",
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Edit", "Write", "Bash(git push*)", "Bash(git commit*)"],
    permissionMode="bypassPermissions",
)


FIXER = AgentDefinition(
    description="Fixes specific code issues identified by review agents.",
    prompt=f"""\
You fix specific findings reported by review agents.
Each finding includes a file, line, severity, and description.
Fix only what is listed — nothing else.

## Method

1. Read the finding's file and surrounding context.
2. Understand the root cause described in the finding.
3. Make the smallest correct change that resolves the issue.
4. Re-read the changed file to verify correctness.
5. After all fixes, run `python -m pytest -x -q --tb=short --no-header`.

## Rules

- One fix per finding. Do not refactor or improve surrounding code.
- If a finding is a false positive, skip it and note why.
- Do not push, commit, or modify git state.

## Code guidelines

{PYTHON_CLEAN_CODE}""",
    model="claude-haiku-4-5-20251001",
    tools=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    disallowedTools=[
        "Bash(git push*)",
        "Bash(git commit*)",
        "Bash(pip install*)",
        "Bash(pip uninstall*)",
    ],
    permissionMode="bypassPermissions",
)


# ── Display ──────────────────────────────────────────────────────


def _tool_detail(block: ToolUseBlock) -> str:
    name = block.name
    inp = block.input
    if name == "Read":
        path = inp.get("file_path", "?")
        return f"Reading {path.split('/')[-1]}" if "/" in path else f"Reading {path}"
    if name == "Grep":
        return f"Grep '{inp.get('pattern', '?')}'"
    if name == "Glob":
        return f"Glob {inp.get('pattern', inp.get('path', '?'))}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"$ {cmd[:60]}" if cmd else "Bash"
    if name == "Edit":
        path = inp.get("file_path", "?")
        return f"Editing {path.split('/')[-1]}" if "/" in path else f"Editing {path}"
    if name == "Write":
        path = inp.get("file_path", "?")
        return f"Writing {path.split('/')[-1]}" if "/" in path else f"Writing {path}"
    return name


class AgentStatus:
    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.coordinator_status = "starting..."
        self.total_tokens = 0
        self.total_cost: float | None = None

    def start(self, task_id: str, description: str) -> None:
        self.agents[task_id] = {
            "name": description,
            "status": "running",
            "action": "starting...",
            "calls": 0,
            "tokens": 0,
        }
        running = sum(1 for a in self.agents.values() if a["status"] == "running")
        self.coordinator_status = f"waiting for {running} agent{'s' if running != 1 else ''}..."

    def progress(self, task_id: str, tokens: int, tool_uses: int = 0) -> None:
        if task_id in self.agents:
            self.agents[task_id]["tokens"] = tokens
            self.agents[task_id]["calls"] = tool_uses
            self.total_tokens = sum(a["tokens"] for a in self.agents.values())

    def done(self, task_id: str, tokens: int | None = None) -> None:
        if task_id in self.agents:
            self.agents[task_id]["status"] = "done"
            self.agents[task_id]["action"] = "complete"
            if tokens is not None:
                self.agents[task_id]["tokens"] = tokens
                self.total_tokens = sum(a["tokens"] for a in self.agents.values())
        running = sum(1 for a in self.agents.values() if a["status"] == "running")
        if running == 0:
            self.coordinator_status = "summarizing results..."
        else:
            self.coordinator_status = f"waiting for {running} agent{'s' if running != 1 else ''}..."

    def render(self) -> Group:
        cost_str = f"  ${self.total_cost:.4f}" if self.total_cost else ""
        header = Text(
            f"Coordinator: {self.coordinator_status}  [{self.total_tokens:,} tokens{cost_str}]",
            style="bold",
        )

        table = Table(show_header=True, expand=True, padding=(0, 1))
        table.add_column("Agent", style="bold cyan", no_wrap=True)
        table.add_column("Status", width=8)
        table.add_column("Activity", style="dim")
        table.add_column("Tokens", justify="right", width=10)
        table.add_column("Tools", justify="right", width=5)

        for info in self.agents.values():
            if info["status"] == "running":
                status = Text("running", style="yellow")
            else:
                status = Text("done", style="green")
            table.add_row(
                info["name"],
                status,
                info["action"][:50],
                f"{info['tokens']:,}",
                str(info["calls"]),
            )
        return Group(header, table)


# ── Main ─────────────────────────────────────────────────────────


async def _run_query(
    options: ClaudeAgentOptions,
    prompt_text: str,
    tracker: AgentStatus,
    console: Console,
) -> ResultMessage | None:
    async def _prompt():
        yield {
            "type": "user",
            "message": {"role": "user", "content": prompt_text},
        }

    result_msg: ResultMessage | None = None
    last_active_tid: str | None = None

    with Live(tracker.render(), console=console, refresh_per_second=4) as live:
        async for message in query(prompt=_prompt(), options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name != "Agent":
                        tid = last_active_tid
                        if tid and tid in tracker.agents and tracker.agents[tid]["status"] == "running":
                            tracker.agents[tid]["action"] = _tool_detail(block)
                        live.update(tracker.render())
            elif isinstance(message, TaskStartedMessage):
                tracker.start(message.task_id, message.description)
                last_active_tid = message.task_id
                live.update(tracker.render())
            elif isinstance(message, TaskProgressMessage):
                last_active_tid = message.task_id
                u = message.usage
                tokens = u["total_tokens"] if isinstance(u, dict) else getattr(u, "total_tokens", 0)
                tools = (u.get("tool_uses", 0) if isinstance(u, dict) else getattr(u, "tool_uses", 0))
                tracker.progress(
                    message.task_id,
                    tokens=tokens,
                    tool_uses=tools,
                )
                live.update(tracker.render())
            elif isinstance(message, TaskNotificationMessage):
                u = message.usage
                if u:
                    final_tokens = u["total_tokens"] if isinstance(u, dict) else getattr(u, "total_tokens", 0)
                else:
                    final_tokens = None
                tracker.done(message.task_id, tokens=final_tokens)
                live.update(tracker.render())
            elif isinstance(message, ResultMessage):
                result_msg = message
                tracker.total_cost = getattr(message, "total_cost_usd", None)
                live.update(tracker.render())

    return result_msg


def _parse_review_result(msg: ResultMessage) -> ReviewResult | None:
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
        import re
        match = re.search(r"```json?\s*\n([\s\S]*?)\n\s*```", text)
        if match:
            return ReviewResult.model_validate_json(match.group(1))
    except Exception:
        pass
    return None


def _print_findings(findings: list[Finding], console: Console) -> None:
    if not findings:
        console.print("\n[green]No findings.[/green]")
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

    console.print(table)


async def main(working_dir: str, allow_fix: bool = True, output_file: str | None = None, target_file: str | None = None) -> None:
    agents = {
        "code_reviewer": CODE_REVIEWER,
        "test_runner": TEST_RUNNER,
    }
    if allow_fix:
        agents["fixer"] = FIXER

    review_options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_PROMPT,
        model="claude-sonnet-4-6",
        cwd=working_dir,
        permission_mode="bypassPermissions",
        agents=agents,
        output_format={"type": "json_schema", "schema": ReviewResult.model_json_schema()},
    )

    console = Console(stderr=True)
    out = Console()
    tracker = AgentStatus()

    # Phase 1: review
    if target_file:
        review_prompt = f"Review only the file {target_file}. Dispatch both review agents scoped to this file and summarize findings."
    else:
        review_prompt = "Run a full quality check on this repository. Dispatch both review agents and summarize findings."

    result_msg = await _run_query(
        review_options,
        review_prompt,
        tracker,
        console,
    )

    review = _parse_review_result(result_msg) if result_msg else None
    if review:
        out.print(f"\n{'─' * 60}")
        out.print(f"[bold]{review.summary}[/bold]")
        out.print(f"Tests passed: {'yes' if review.tests_passed else 'no'}")
        _print_findings(review.findings, out)
        if output_file:
            Path(output_file).write_text(
                review.model_dump_json(indent=2), encoding="utf-8"
            )
            out.print(f"\nResults written to {output_file}")
    elif result_msg:
        out.print(f"\n{'─' * 60}")
        out.print(getattr(result_msg, "result", "") or "(no output)")

    if not allow_fix or not review or not review.findings:
        return

    # Phase 2: ask user if they want to fix
    out.print(f"\n{'─' * 60}")
    choice = input("Fix issues? [all / high+ / none]: ").strip().lower()
    if choice in ("none", "n", "no", "q", ""):
        return

    # Phase 3: dispatch fixer
    if choice in ("high", "high+"):
        to_fix = [f for f in review.findings if f.severity == "HIGH"]
    else:
        to_fix = review.findings

    fix_options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_PROMPT,
        model="claude-haiku-4-5-20251001",
        cwd=working_dir,
        permission_mode="bypassPermissions",
        agents={"fixer": FIXER},
    )
    findings_json = json.dumps([f.model_dump() for f in to_fix], indent=2)
    tracker.coordinator_status = "dispatching fixer..."
    fix_result = await _run_query(
        fix_options,
        f"Fix these {len(to_fix)} findings. Dispatch the fixer agent with this list:\n\n{findings_json}",
        tracker,
        console,
    )

    if fix_result:
        out.print(f"\n{'─' * 60}")
        out.print(getattr(fix_result, "result", "") or "(no output)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multiagent code review")
    parser.add_argument("working_dir", nargs="?", default=".", help="Repo path")
    parser.add_argument("--no-fix", action="store_true", help="Skip fix prompt")
    parser.add_argument("-o", "--output", help="Write structured results to JSON file")
    parser.add_argument("--file", help="Review a single file instead of the whole repo")
    args = parser.parse_args()
    asyncio.run(main(args.working_dir, allow_fix=not args.no_fix, output_file=args.output, target_file=args.file))
