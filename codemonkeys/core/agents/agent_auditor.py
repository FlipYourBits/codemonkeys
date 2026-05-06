"""Agent auditor — analyzes another agent's logs against its source code.

Reads the target agent's .py file to extract the contract (prompt, tools,
output schema, guardrails), then compares against LogMetrics JSON to verify
the agent behaved correctly and efficiently.

Also provides:
- A prompt fixer agent that modifies agent source files to address findings
- Interactive display/prompt helpers for the CLI audit flow
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import AgentDefinition
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

AGENT_SOURCES: dict[str, str] = {
    "python_file_reviewer": "codemonkeys/core/agents/python_file_reviewer.py",
    "architecture_reviewer": "codemonkeys/core/agents/architecture_reviewer.py",
    "changelog_reviewer": "codemonkeys/core/agents/changelog_reviewer.py",
    "readme_reviewer": "codemonkeys/core/agents/readme_reviewer.py",
    "python_code_fixer": "codemonkeys/core/agents/python_code_fixer.py",
    "python_implementer": "codemonkeys/core/agents/python_implementer.py",
    "python_characterization_tester": "codemonkeys/core/agents/python_characterization_tester.py",
    "python_structural_refactorer": "codemonkeys/core/agents/python_structural_refactorer.py",
    "spec_compliance_reviewer": "codemonkeys/core/agents/spec_compliance_reviewer.py",
}


def make_agent_auditor(agent_source_path: str) -> AgentDefinition:
    """Create an auditor agent that evaluates another agent's log against its source code."""
    return AgentDefinition(
        description=f"Audit agent behavior from logs vs source: {agent_source_path}",
        prompt=f"""\
You are an agent auditor. Your job is to analyze whether another agent
performed its task correctly and efficiently by comparing its source code
against its actual execution log.

## Step 1: Read the Agent Source

Read the agent source file at: {agent_source_path}

Extract from it:
- The agent's intended purpose (from the description and prompt text)
- The list of approved tools
- Any specific constraints or guardrails (e.g., "read-only", "do NOT modify files")
- The expected output format/schema
- Any method instructions (what steps the agent should follow)

## Step 2: Analyze the Log Metrics

The user prompt contains a JSON object with the full execution log metrics.
Analyze it for the following issues:

### Instruction Compliance
Did the agent follow its system prompt? Look for:
- Read-only agents that tried to write or modify files
- Agents that ignored specific constraints in their prompt
- Agents that skipped required steps from the method section
- Agents that produced output not matching the expected format

### Tool Discipline (Hard Violations)
The `unauthorized_tool_calls` field pre-flags tools not in the allowed list.
Confirm each one and explain the violation.

### Tool Discipline (Appropriateness)
Even for allowed tools, check whether each tool call was relevant to the
task. Look at the `tool_calls` list and the agent's `user_prompt` to judge:
- Did the agent read files unrelated to its task?
- Did the agent run commands outside the scope of its purpose?
- Were tool calls proportionate to the task complexity?

### Turn Efficiency
Look at the `turns` list and `repeated_tool_calls` for:
- Same file read more than once (the `repeated_tool_calls` field flags these)
- Redundant information gathering (grepping for something already found)
- Turns that produced no useful progress
- Excessive thinking without action

### Focus
Read the `thinking_content` in each turn. Flag:
- Extended reasoning about topics outside the agent's task
- Confusion about what to do next
- Tangential exploration of unrelated concerns

### Output Correctness
Compare the `structured_output` against the expected output schema from
the agent source. Check:
- Does it match the expected structure?
- Are fields populated with sensible values?
- Did the agent return findings about things it wasn't asked to review?

## Output Format

Return your findings as structured JSON matching the AgentAudit schema.

Verdict rules:
- "fail" if ANY issue has category: unauthorized_tool, instruction_violation,
  off_task, or output_problem
- "pass" if only efficiency issues (repeated_tool_call, wasted_turn,
  inappropriate_tool_use) — flag them in issues but pass the agent

Always include:
- A 2-3 sentence summary of what the agent did
- A token_assessment noting whether usage was reasonable
- Specific recommendations for prompt improvements if issues were found

## Guardrails

You are a **read-only auditor**. Do NOT modify any files. Only read the
agent source file specified above. Do not read any other files.""",
        model="sonnet",
        tools=["Read"],
        permissionMode="dontAsk",
    )


def make_agent_prompt_fixer(
    agent_source_path: str, selected_fixes: list[dict[str, Any]]
) -> AgentDefinition:
    """Create a fixer agent that modifies an agent's source to address audit findings."""
    fixes_text = json.dumps(selected_fixes, indent=2)
    return AgentDefinition(
        description=f"Fix agent prompt based on audit findings: {agent_source_path}",
        prompt=f"""\
You are an agent prompt engineer. Your job is to modify an agent's factory
file to address specific audit findings selected by the user.

## Target File

Read and edit: {agent_source_path}

## Selected Fixes

{fixes_text}

## How to Fix Each Category

- **unauthorized_tool**: Strengthen the prompt to explicitly forbid that tool,
  or remove it from the tools list if it shouldn't be available.
- **instruction_violation**: Strengthen the relevant constraint in the prompt.
  Make the rule more prominent or add an explicit "Do NOT" statement.
- **inappropriate_tool_use**: Add clearer scoping for when each tool should
  be used (e.g., "Only read files listed in the user prompt").
- **repeated_tool_call**: Add efficiency guidance (e.g., "Do not re-read
  files you have already read").
- **wasted_turn**: Add focus guidance to reduce unnecessary deliberation.
- **off_task**: Tighten the focus section — add explicit boundaries for
  what is and is not in scope.
- **output_problem**: Clarify the expected output format or add examples.
- **recommendation**: Apply the suggestion as a targeted prompt improvement.

## Rules

- Read the agent source file first to understand its current state.
- Make targeted edits — do not rewrite the entire prompt.
- Preserve the existing code structure, formatting, and style.
- After editing, briefly describe what you changed and why.""",
        model="sonnet",
        tools=["Read", "Edit"],
        permissionMode="dontAsk",
    )


def display_audit_results(
    console: Console, audit: dict[str, Any], agent_name: str
) -> None:
    """Display audit results with numbered issues and recommendations."""
    verdict = audit.get("verdict", "?")
    style = "green" if verdict == "pass" else "red"

    lines = [f"[bold]Summary:[/bold] {audit.get('summary', 'N/A')}"]
    lines.append(f"[bold]Tokens:[/bold] {audit.get('token_assessment', 'N/A')}")

    issues = audit.get("issues", [])
    recommendations = audit.get("recommendations", [])

    if issues:
        lines.append("")
        lines.append("[bold]Issues:[/bold]")
        for i, issue in enumerate(issues, 1):
            turn = f" (turn {issue['turn']})" if issue.get("turn") else ""
            lines.append(f"  [{style}][{i}][/{style}] {issue['category']}{turn}")
            lines.append(f"      {issue['description']}")

    if recommendations:
        lines.append("")
        lines.append("[bold]Recommendations:[/bold]")
        offset = len(issues) + 1
        for i, rec in enumerate(recommendations):
            lines.append(f"  [cyan][{offset + i}][/cyan] {rec}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[{style}]{agent_name}: {verdict.upper()}[/{style}]",
            border_style=style,
        )
    )


def prompt_for_fixes(
    console: Console, audit: dict[str, Any]
) -> list[dict[str, Any]]:
    """Prompt user to select issues/recommendations to fix. Returns selected items."""
    issues = audit.get("issues", [])
    recommendations = audit.get("recommendations", [])

    total = len(issues) + len(recommendations)
    if total == 0:
        return []

    response = Prompt.ask(
        "\n[bold]Fix issues?[/bold] Enter numbers (e.g. 1,3), [cyan]all[/cyan], or [dim]skip[/dim]",
        default="skip",
    )

    if response.strip().lower() == "skip":
        return []

    if response.strip().lower() == "all":
        selected_indices = list(range(1, total + 1))
    else:
        try:
            selected_indices = [int(x.strip()) for x in response.split(",")]
        except ValueError:
            console.print("[yellow]Invalid input, skipping fixes[/yellow]")
            return []

    selected: list[dict[str, Any]] = []
    for idx in selected_indices:
        if 1 <= idx <= len(issues):
            selected.append({"type": "issue", **issues[idx - 1]})
        elif len(issues) < idx <= total:
            rec_idx = idx - len(issues) - 1
            selected.append(
                {"type": "recommendation", "description": recommendations[rec_idx]}
            )
        else:
            console.print(f"[yellow]Index {idx} out of range, skipping[/yellow]")

    return selected


async def run_audit_with_fixes(
    console: Console,
    runner: Any,
    audit_result: dict[str, Any],
    agent_name: str,
    source_path: str,
) -> None:
    """Display audit, prompt for fixes, and run fixer agent if requested."""
    display_audit_results(console, audit_result, agent_name)

    selected = prompt_for_fixes(console, audit_result)
    if not selected:
        return

    fixer = make_agent_prompt_fixer(source_path, selected)
    console.print(f"\n[bold]Applying {len(selected)} fix(es) to {source_path}...[/bold]")

    fix_result = await runner.run_agent(
        fixer,
        "Apply the selected fixes to the agent source file.",
        agent_name="agent_prompt_fixer",
    )

    if fix_result.text:
        console.print(
            Panel(
                fix_result.text[:2000],
                title="[green]Fixes Applied[/green]",
                border_style="green",
            )
        )
    else:
        console.print("[green]Fixes applied.[/green]")
