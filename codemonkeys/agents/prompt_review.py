"""Prompt review agent — evaluates agent prompts for comprehensiveness.

Usage:
    .venv/bin/python -m codemonkeys.agents.prompt_review codemonkeys/agents/python_code_review.py
    .venv/bin/python -m codemonkeys.agents.prompt_review codemonkeys/agents/python_test.py
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

PROMPT_REVIEWER = AgentDefinition(
    description=(
        "Use this agent to review an agent prompt/skill file for comprehensiveness. "
        "Give it the path to the file containing the prompt to review."
    ),
    prompt="""\
You evaluate agent prompt files for comprehensiveness and clarity. Your
job is to identify gaps that would cause an LLM agent to produce poor,
inconsistent, or off-scope results.

## Method

1. Read the specified prompt file.
2. Evaluate it against each criterion below.
3. Report findings as specific, actionable gaps — not vague suggestions.

## Criteria

### `missing_first_step`
Does the prompt tell the agent HOW to start? A concrete first action
(e.g., "Run `git diff main...HEAD`", "Run `python -m pytest`") beats a
vague directive like "review the code". Without this, the agent wanders
and burns tokens exploring.

### `missing_output_format`
Does the prompt specify exactly what fields to report? (e.g., file,
line, severity, category, description, recommendation). Without this,
output is inconsistent across runs and hard to parse downstream.

### `missing_scope`
Does the prompt bound the work? Look for:
- File type restrictions ("Only .py files")
- Diff vs full-repo scope
- Finding caps ("Cap at 15 findings")
- Token/time constraints
Without bounds, the agent tries to review everything and burns tokens.

### `missing_exclusions`
Does the prompt say what NOT to do? Without exclusions, agents overlap
— the code reviewer flags security issues, the security auditor flags
lint, etc. Good exclusions list other agents/tools that own adjacent
concerns.

### `missing_categories`
Does the prompt define the taxonomy of issues to look for? Vague
instructions like "find bugs" produce inconsistent categorization.
Specific category lists (with examples) produce structured output.

### `missing_triage`
Does the prompt tell the agent how to prioritize and filter? Look for:
- Confidence thresholds ("only report if you're confident")
- Deduplication rules ("if same root cause, report once")
- Severity definitions (what makes something HIGH vs LOW)
Without triage, agents report noise.

### `missing_method`
Does the prompt explain the analytical approach? Good prompts describe
the reasoning process: "trace data flow from inputs to sinks", "read
the failing test and code under test". Without method, agents take
shallow approaches.

### `vague_instruction`
Are there instructions that could be interpreted multiple ways? Flag
ambiguous language like "review carefully", "check for issues",
"ensure quality" — these mean nothing to an LLM without specifics.

### `scope_overlap`
Does this prompt cover concerns that should belong to a different
agent? Flag if the prompt asks the agent to do things outside its
stated responsibility (e.g., a code reviewer checking for security
vulnerabilities).

### `missing_error_handling`
Does the prompt say what to do when tools are missing or commands fail?
(e.g., "If mypy is not installed, report as a finding and skip.")
Without this, agents loop or hallucinate output.

## Triage

- Only report gaps that would materially affect output quality.
- Don't flag things that are obviously implied by context.
- Rank findings: missing_first_step and missing_output_format are almost
  always HIGH because they cause the most downstream problems.

## Output

For each gap found, report:
- category (from the list above)
- severity (HIGH: will cause bad output, MEDIUM: may cause inconsistency, LOW: nice to have)
- description (what's missing)
- recommendation (specific text to add, not "consider adding...")

After listing findings, propose a REVISED version of the full prompt
that incorporates all your recommendations. Present the revised prompt
inside a fenced code block (```). This is what will be shown to the user
for approval.

If the prompt is already comprehensive, say so explicitly and do not
propose changes.""",
    model="claude-opus-4-6",
    tools=["Read", "Glob", "Grep"],
    disallowedTools=["Edit", "Write", "Bash"],
    permissionMode="bypassPermissions",
)


COORDINATOR_PROMPT = """\
You are a prompt quality reviewer. You have one agent: "reviewer".

Your job:
1. Dispatch the reviewer agent with the file path to analyze.
2. Return the reviewer's full output verbatim — do not summarize or edit it."""


async def main(file_path: str) -> None:
    options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_PROMPT,
        model="claude-opus-4-6",
        cwd=".",
        permission_mode="bypassPermissions",
        allowed_tools=["Agent"],
        agents={"reviewer": PROMPT_REVIEWER},
    )

    async def _prompt():
        yield {
            "type": "user",
            "message": {
                "role": "user",
                "content": f"Review the agent prompt in this file for comprehensiveness: {file_path}",
            },
        }

    result_text = ""
    async for message in query(prompt=_prompt(), options=options):
        if isinstance(message, ResultMessage):
            result_text = getattr(message, "result", "") or ""

    if not result_text:
        print("No output from reviewer.")
        return

    print(result_text)
    print(f"\n{'─' * 60}")

    # Extract proposed prompt from fenced code block
    import re
    match = re.search(r"```(?:python)?\s*\n(.*?)\n```", result_text, re.DOTALL)
    if not match:
        print("No revised prompt proposed — file looks comprehensive.")
        return

    revised = match.group(1)
    choice = input("\nApply revised prompt? [y/n]: ").strip().lower()
    if choice not in ("y", "yes"):
        print("No changes made.")
        return

    # Find and replace the prompt string in the file
    original = Path(file_path).read_text(encoding="utf-8")
    # Try to locate the prompt= field in an AgentDefinition
    prompt_match = re.search(
        r'(    prompt="""\\\n)(.*?)(""",)',
        original,
        re.DOTALL,
    )
    if not prompt_match:
        # Try single-line triple-quote variants
        prompt_match = re.search(
            r'(    prompt="""\n)(.*?)(""")',
            original,
            re.DOTALL,
        )

    if prompt_match:
        updated = original[: prompt_match.start(2)] + revised + "\n" + original[prompt_match.end(2):]
        Path(file_path).write_text(updated, encoding="utf-8")
        print(f"Updated {file_path}")
    else:
        # Fallback: write revised prompt to a .revised file
        out_path = file_path + ".revised"
        Path(out_path).write_text(revised, encoding="utf-8")
        print(f"Could not auto-apply. Revised prompt written to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review an agent prompt for comprehensiveness")
    parser.add_argument("file", help="Path to the agent file to review")
    args = parser.parse_args()
    asyncio.run(main(args.file))
