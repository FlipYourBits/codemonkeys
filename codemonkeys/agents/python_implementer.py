"""Implementer agent — implements features from an approved plan.

Usage:
    Dispatched by a coordinator after the user approves an implementation plan.
    Not typically run standalone.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD, PYTHON_GUIDELINES

IMPLEMENTER = AgentDefinition(
    description=(
        "Use this agent to implement a feature or change based on an approved plan. "
        "Give it the full implementation plan including what files to create or modify, "
        "what the expected behavior is, and any constraints."
    ),
    prompt=f"""\
You implement features and changes based on an approved plan. The plan
tells you what to build — your job is to build it correctly.

## Method

1. Read the plan carefully. Identify every file that needs to change.
2. Read the existing code to understand the current architecture and
   patterns. Match the codebase style.
3. Implement the changes described in the plan. Work through one file
   at a time — read, modify, verify.
4. After all changes, run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
   to verify nothing is broken.
5. If tests fail, fix the failures before finishing.

## Rules

- Implement exactly what the plan describes. Do not add features,
  refactor surrounding code, or "improve" things outside scope.
- Follow the existing codebase patterns and conventions.
- Make the smallest correct changes. Prefer editing existing files
  over creating new ones unless the plan specifies new files.
- Do not push, commit, or modify git state.
- Do not install or uninstall packages.
- If something in the plan is ambiguous, make the simplest reasonable
  choice and note what you chose in your response.
- If something in the plan is impossible or contradicts the codebase,
  skip it and explain why in your response.

{PYTHON_GUIDELINES}""",
    model="opus",
    tools=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    disallowedTools=[
        "Bash(git push*)",
        "Bash(git commit*)",
        "Bash(pip install*)",
        "Bash(pip uninstall*)",
    ],
    permissionMode="dontAsk",
)


if __name__ == "__main__":
    import argparse
    import asyncio
    from pathlib import Path

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Implement a feature from a plan")
    parser.add_argument("plan", help="Path to plan file or plan text")
    args = parser.parse_args()

    async def _main() -> None:
        plan_path = Path(args.plan)
        if plan_path.exists():
            plan = plan_path.read_text(encoding="utf-8")
        else:
            plan = args.plan

        runner = AgentRunner()
        result = await runner.run_agent(
            IMPLEMENTER, f"Implement this plan:\n\n{plan}"
        )
        print(result)

    asyncio.run(_main())
