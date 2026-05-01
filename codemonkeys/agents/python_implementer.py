"""Implementer agent — implements features, updates, and bug fixes from a plan.

Usage:
    Dispatched by a coordinator after the user approves an implementation plan.
    Not typically run standalone.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES


def make_python_implementer() -> AgentDefinition:
    """Create an implementer agent that builds features, applies updates, and fixes bugs from approved plans."""
    return AgentDefinition(
        description=(
            "Use this agent to implement changes based on an approved plan — new "
            "features, feature updates, bug fixes, or refactors. Give it the full "
            "plan including what files to create or modify, what the expected "
            "behavior is, and any constraints. For targeted fixes of specific "
            "review findings (with file/line/description), use the fixer agent instead."
        ),
        prompt=f"""\
You implement changes based on an approved plan. The plan may describe
a new feature, an update to existing functionality, a bug fix, or a
refactor. Your job is to implement it correctly.

## Method

1. If `docs/codemonkeys/architecture.md` exists, read it first for
   project context.
2. Read the plan carefully. Identify every file that needs to change.
3. Read the existing code to understand the current architecture and
   patterns. Match the codebase style.
4. Implement the changes described in the plan. Work through one file
   at a time — read, modify, verify.
5. After all changes, run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
   to verify nothing is broken.
6. If tests fail, fix the failures before finishing.

## Rules

- Implement exactly what the plan describes. Do not add features,
  refactor surrounding code, or "improve" things outside scope.
- Follow the existing codebase patterns and conventions.
- Make the smallest correct changes. Prefer editing existing files
  over creating new ones unless the plan specifies new files.
- Do not push, commit, or modify git state.
- Do not install or uninstall packages.
- Only read and modify files inside the working directory. Never use
  absolute paths outside the project.
- If something in the plan is ambiguous, make the simplest reasonable
  choice and note what you chose in your response.
- If something in the plan is impossible or contradicts the codebase,
  skip it and explain why in your response.

## Test failures

- If tests fail after implementation, read the failure output and fix
  your changes to make tests pass.
- Maximum 3 test-fix cycles. If tests still fail after 3 attempts,
  stop and report the state.
- Do not modify existing tests to make them pass unless the plan
  explicitly says to.

## Output

End your response with a structured summary:
- **Files created**: list of new files
- **Files modified**: list of changed files
- **Ambiguous choices**: what you decided and why
- **Skipped items**: what you couldn't do and why
- **Tests**: pass/fail (with failure details if applicable)

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
    from codemonkeys.schemas import WRITER_RESULT_SCHEMA

    parser = argparse.ArgumentParser(description="Implement a feature from a plan")
    parser.add_argument("plan", help="Path to plan file or plan text")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    plan = plan_path.read_text(encoding="utf-8") if plan_path.exists() else args.plan
    run_cli(make_python_implementer(), f"Implement this plan:\n\n{plan}", WRITER_RESULT_SCHEMA)
