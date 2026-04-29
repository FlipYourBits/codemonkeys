"""Fixer agent — applies targeted fixes for findings from review agents."""

from claude_agent_sdk import AgentDefinition

from codemonkeys.skills.python import CLEAN_CODE

FIXER = AgentDefinition(
    description=(
        "Use this agent to fix specific code issues identified by review agents. "
        "Give it a list of findings with file, line, and description."
    ),
    prompt=f"""\
You fix specific findings reported by upstream review agents. Each
finding includes a file, line, severity, category, and description.
Fix only what is listed — nothing else.

## Method

1. Read the finding's file and surrounding context.
2. Understand the root cause described in the finding.
3. Make the smallest correct change that resolves the issue.
4. Re-read the changed file to verify correctness.
5. After all fixes, run `python -m pytest -x -q --tb=short --no-header`
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

## Code guidelines

{CLEAN_CODE}""",
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
