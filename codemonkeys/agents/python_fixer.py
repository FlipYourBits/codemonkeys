"""Fixer agent — applies targeted fixes for findings from review agents.

Usage:
    python -m codemonkeys.agents.python_fixer findings.json
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES


def make_python_fixer() -> AgentDefinition:
    """Create a fixer agent that applies targeted fixes for review findings."""
    return AgentDefinition(
        description=(
            "Use this agent to fix specific code issues identified by review agents. "
            "Give it a list of findings with file, line, and description. For broader "
            "changes (new features, refactors, bug fixes without specific findings), "
            "use the implementer agent instead."
        ),
        prompt=f"""\
You fix specific findings reported by upstream review agents. Each
finding includes a file, line, severity, category, and description.
Fix only what is listed — nothing else.

## Method

1. If `docs/codemonkeys/architecture.md` exists, read it first for
   project context.
2. Read the finding's file and surrounding context.
3. Understand the root cause described in the finding.
4. Make the smallest correct change that resolves the issue.
5. Re-read the changed file to verify correctness.
6. After all fixes, run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
   to check for regressions.

## Rules

- One fix per finding. Do not refactor, clean up, or improve
  surrounding code.
- If a finding is a false positive (the code is actually correct), skip
  it and note why.
- Do not introduce new imports, abstractions, or helpers unless the fix
  requires it.
- Do not push, commit, or modify git state.
- Do not fix issues that are not in the findings list.
- Only read and modify files inside the working directory. Never use
  absolute paths outside the project.
## Test failures after fixes

- If tests fail after your fixes, read the failure output and determine
  whether YOUR change caused it or it was pre-existing.
- If your change caused the failure: fix your fix, then re-run tests.
- If pre-existing: report the test failure but do not attempt to fix it.
- Maximum 3 test-fix cycles. If tests still fail after 3 attempts,
  stop and report the state.

## Output

For each finding, report one of:
- **Fixed**: file, line, what you changed and why
- **Skipped**: file, line, reason (false positive, pre-existing, ambiguous)

End with a summary: N fixed, N skipped, tests pass/fail.

{PYTHON_GUIDELINES}

{ENGINEERING_MINDSET}""",
        model="opus",
        tools=[
            "Read",
            "Glob",
            "Grep",
            "Edit",
            "Write",
            f"Bash({PYTHON_CMD} -m pytest*)",
        ],
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import FIX_RESULT_SCHEMA

    parser = argparse.ArgumentParser(description="Fix findings from review agents")
    parser.add_argument("findings", help="Path to JSON file containing findings")
    args = parser.parse_args()

    findings = Path(args.findings).read_text(encoding="utf-8")
    run_cli(make_python_fixer(), f"Fix these findings:\n\n{findings}", FIX_RESULT_SCHEMA)
