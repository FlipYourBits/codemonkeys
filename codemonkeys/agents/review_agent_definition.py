"""AgentDefinition reviewer — evaluates description, prompt, permissions, and model.

Usage:
    .venv/bin/python -m codemonkeys.agents.review_agent_definition codemonkeys/agents/python_code_review.py
    .venv/bin/python -m codemonkeys.agents.review_agent_definition codemonkeys/agents/ -o results.json
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from claude_agent_sdk import AgentDefinition
from pydantic import BaseModel, Field


class DefinitionFinding(BaseModel):
    file: str = Field(description="Path to the reviewed file")
    area: Literal["description", "prompt", "permissions", "model"] = Field(
        description="Which part of the AgentDefinition has the issue",
    )
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    description: str = Field(description="What is wrong or missing")
    recommendation: str = Field(description="Specific change to make")


class DefinitionReviewResult(BaseModel):
    findings: list[DefinitionFinding] = Field(default_factory=list)
    summary: str = Field(description="Brief overall assessment")


def make_definition_reviewer(target: str | None = None) -> AgentDefinition:
    if target and Path(target).is_file():
        first_step = (
            f"1. Read `{target}`.\n"
            "2. Identify the AgentDefinition instance and extract each field."
        )
    else:
        location = f"under `{target}`" if target and Path(target).is_dir() else "in the current working directory"
        first_step = (
            f"1. Recursively find all `.py` files {location} that contain "
            "AgentDefinition instances.\n"
            "2. For each definition, extract each field (description, prompt, "
            "model, tools, disallowedTools, permissionMode)."
        )

    return AgentDefinition(
        description=(
            "Use this agent to review an AgentDefinition file for correctness. "
            "Give it the path to a Python file containing an AgentDefinition, "
            "or a directory to recursively review every AgentDefinition under it."
        ),
        prompt=f"""\
You review AgentDefinition instances for correctness and completeness.
An AgentDefinition has: description, prompt, model, tools,
disallowedTools, and permissionMode. You evaluate every aspect.

## Method

{first_step}
3. Evaluate each field against the criteria below.
4. Report findings as specific, actionable gaps — not vague suggestions.

## Criteria

### Description Review

The `description` field is the ONLY thing a coordinator sees when
deciding whether to dispatch this agent. Evaluate:

- **clarity**: Would a coordinator unambiguously understand when to use
  this agent vs. other agents? The description must answer: "What does
  this agent do?" and "When should I dispatch it?"
- **specificity**: Does it name the concrete capability (e.g., "run mypy
  type checking") or is it vague ("checks code quality")?
- **differentiation**: Could this description be confused with another
  agent's responsibility? It should make the boundary clear.
- **action-oriented**: Does it tell the coordinator HOW to use it
  (e.g., "Give it a list of findings with file, line, and description")?

### Prompt Review

The `prompt` field is the agent's full instructions. Evaluate:

- **first_step**: Does the prompt tell the agent HOW to start? A
  concrete first action (e.g., "Run `python -m pytest`") beats a vague
  directive like "review the code".
- **output_format**: Does it specify exactly what fields to report?
  (e.g., file, line, severity, category, description, recommendation).
- **scope**: Does it bound the work? Look for file type restrictions,
  diff vs full-repo scope, finding caps, token/time constraints.
- **exclusions**: Does it say what NOT to do? Without exclusions, agents
  overlap with other agents. Good exclusions list adjacent concerns and
  which agent owns them.
- **categories**: Does it define the taxonomy of issues to look for?
  Specific category lists produce structured output.
- **triage**: Does it tell the agent how to prioritize and filter?
  Confidence thresholds, deduplication rules, severity definitions.
- **method**: Does it explain the analytical approach and reasoning
  process, not just what to find?
- **vague_instructions**: Flag ambiguous language like "review
  carefully", "check for issues", "ensure quality" — these mean nothing
  to an LLM without specifics.
- **error_handling**: Does it say what to do when tools are missing or
  commands fail?

### Permission Review

Evaluate whether the combination of `tools`, `disallowedTools`, and
`permissionMode` is appropriate for the agent's task:

- **tools scope**: Are any tools listed that the agent doesn't need
  based on its prompt? Are any tools missing that the prompt requires?
  (e.g., prompt says "run pytest" but Bash is not in tools)
- **write safety**: If the agent is read-only (report findings, don't
  fix), it should NOT have Edit or Write in its tools list.
- **disallowedTools coverage**: Are dangerous patterns blocked? Agents
  that use Bash should typically block `git push*`, `git commit*`, and
  `pip install*` unless explicitly needed.
- **permissionMode fit**: `dontAsk` is correct for unattended agents
  that should never prompt the user. `bypassPermissions` auto-approves
  everything — flag if used on agents with broad tool access.
  `plan` is correct for read-only agents. Flag mismatches between the
  permission mode and the agent's intended behavior.
- **principle of least privilege**: Does the agent have the minimum
  tools and permissions needed for its task?

### Model Review

Evaluate whether the model choice fits the task complexity:

- **haiku**: Fast, cheap. Right for mechanical tasks — run a command,
  parse structured output, classify results. Linting, test running,
  dependency scanning.
- **sonnet**: Balanced. Good for tasks needing judgment but not deep
  reasoning. Standard code review, documentation review.
- **opus**: Deep reasoning, expensive. Right for complex analysis —
  security audits, architecture review, prompt engineering, multi-step
  debugging.

Flag if the model seems over- or under-powered for the task described
in the prompt. A linter that just runs ruff and parses output doesn't
need opus. A security auditor tracing data flows shouldn't use haiku.

## Triage

- Only report things that need to CHANGE. If a field is already
  correct (e.g., model is appropriate, permissions are right), do NOT
  create a finding for it. A finding means "this should be different."
- Only report gaps that would materially affect agent behavior.
- Don't flag things obviously implied by context.
- Rank by impact: permission/safety issues are always HIGH, missing
  output format is HIGH, model mismatch is MEDIUM.

## Edge cases

- If a file imports `AgentDefinition` but does not instantiate one (e.g., a re-exporter or test), skip it silently.
- If a file has multiple AgentDefinition instances, evaluate each separately and emit findings keyed by `file` plus a clear identifier in the description.
- If a definition cannot be parsed, emit one HIGH finding describing the parse failure rather than guessing.

## Output

For each finding, report:
- area (description / prompt / permissions / model)
- severity (HIGH / MEDIUM / LOW)
- description (what's wrong or missing)
- recommendation (specific text or change, not "consider adding...")

If the definition is already solid, say so in the summary and return
an empty findings list.""",
        model="opus",
        tools=["Read", "Glob", "Grep"],
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    from codemonkeys.runner import AgentRunner

    def _find_definition_files(target: Path) -> list[Path]:
        if target.is_file():
            return [target]
        return sorted(
            p for p in target.rglob("*.py")
            if "AgentDefinition" in p.read_text(encoding="utf-8")
        )

    def _print_result(result: DefinitionReviewResult, console: Console) -> None:
        console.print(f"\n[bold]{result.summary}[/bold]")
        if not result.findings:
            console.print("  [green]No findings.[/green]")
            return

        severity_styles = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
        table = Table(show_header=True, expand=True, padding=(0, 1), show_lines=True)
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Sev", width=8)
        table.add_column("Area", style="cyan", width=14)
        table.add_column("Description")
        table.add_column("Recommendation", style="dim")

        for i, finding in enumerate(result.findings, 1):
            style = severity_styles.get(finding.severity, "")
            table.add_row(
                str(i),
                Text(finding.severity, style=style),
                finding.area,
                finding.description,
                finding.recommendation,
            )
        console.print(table)

    def _parse_result(msg: object) -> DefinitionReviewResult | None:
        structured = getattr(msg, "structured_output", None)
        if not structured:
            return None
        if isinstance(structured, str):
            structured = json.loads(structured)
        return DefinitionReviewResult.model_validate(structured)

    from codemonkeys.agents.python_fixer import make_python_fixer

    parser = argparse.ArgumentParser(description="Review AgentDefinitions for correctness")
    parser.add_argument("path", nargs="?", default=".", help="Agent .py file or folder (default: cwd)")
    parser.add_argument("--no-fix", action="store_true", help="Skip the fix prompt")
    parser.add_argument("-o", "--output", help="Write structured results to a JSON file")
    args = parser.parse_args()

    async def _main() -> None:
        console = Console(stderr=True)
        files = _find_definition_files(Path(args.path))
        if not files:
            console.print(f"[yellow]No AgentDefinition files found under {args.path}[/yellow]")
            return

        output_format = {"type": "json_schema", "schema": DefinitionReviewResult.model_json_schema()}
        runner = AgentRunner()
        all_findings: list[dict] = []
        all_results: list[dict] = []

        for i, file_path in enumerate(files):
            if i > 0:
                console.print(f"\n{'─' * 60}\n")
            console.print(f"[bold cyan]Reviewing {file_path}...[/bold cyan]")

            await runner.run_agent(
                make_definition_reviewer(),
                f"Review the AgentDefinition in this file: {file_path}",
                output_format=output_format,
            )

            console.print("[dim]Preparing summary...[/dim]")
            result = _parse_result(runner.last_result) if runner.last_result else None
            if result:
                _print_result(result, console)
                all_results.append(result.model_dump())
                for finding in result.findings:
                    all_findings.append(finding.model_dump())
            else:
                text = getattr(runner.last_result, "result", None) or "No output."
                console.print(text)

        if args.output and all_results:
            Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
            console.print(f"\nResults written to {args.output}")

        if args.no_fix or not all_findings:
            if not all_findings:
                console.print("\n[green]No fixes needed.[/green]")
            return

        numbered = {i: f for i, f in enumerate(all_findings, 1)}
        console.print(f"\n{'─' * 60}")
        console.print('What would you like to fix? (e.g. "all", "1 3 4", "1,2", "no" to skip)')
        instructions = input('> ').strip()
        if not instructions or instructions.lower() in ("no", "none", "exit", "quit", "q"):
            return

        if "all" in instructions.lower():
            to_fix = list(numbered.values())
        else:
            import re
            requested = [int(n) for n in re.findall(r"\d+", instructions)]
            to_fix = [numbered[n] for n in requested if n in numbered]
            invalid = [n for n in requested if n not in numbered]
            if invalid:
                console.print(f"[yellow]Skipping invalid numbers: {invalid}[/yellow]")
            if not to_fix:
                console.print("[yellow]No valid findings selected.[/yellow]")
                return

        findings_json = json.dumps(to_fix, indent=2)
        console.print(f"[bold cyan]Fixing {len(to_fix)} finding{'s' if len(to_fix) != 1 else ''}...[/bold cyan]")
        fix_result = await runner.run_agent(
            make_python_fixer(),
            f"Fix these AgentDefinition issues:\n\n{findings_json}\n\n"
            f"After fixing, summarize what you changed: which findings you "
            f"fixed, what files you modified, and any findings you skipped "
            f"(with the reason).",
        )
        console.print(f"\n{'─' * 60}")
        console.print("[bold]Fix summary:[/bold]")
        console.print(fix_result or "No output from fixer.")

    asyncio.run(_main())
