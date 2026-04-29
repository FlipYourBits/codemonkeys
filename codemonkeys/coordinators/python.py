"""Python coordinator — interactive session with constrained Python agents.

An interactive Claude session with deep Python expertise and specialized
agents for linting, testing, type checking, code review, security audit,
and implementation. You chat with the coordinator; it dispatches agents.

Usage:
    .venv/bin/python -m codemonkeys.coordinators.python
    .venv/bin/python -m codemonkeys.coordinators.python --cwd /path/to/project
"""

from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions

from codemonkeys.agents import (
    CODE_REVIEWER,
    DEP_AUDITOR,
    DOCS_REVIEWER,
    FIXER,
    IMPLEMENTER,
    LINTER,
    SECURITY_AUDITOR,
    TEST_RUNNER,
    TEST_WRITER,
    TYPE_CHECKER,
)

PYTHON_AGENTS = {
    "linter": LINTER,
    "type_checker": TYPE_CHECKER,
    "test_runner": TEST_RUNNER,
    "dep_auditor": DEP_AUDITOR,
    "test_writer": TEST_WRITER,
    "code_reviewer": CODE_REVIEWER,
    "security_auditor": SECURITY_AUDITOR,
    "docs_reviewer": DOCS_REVIEWER,
    "fixer": FIXER,
    "implementer": IMPLEMENTER,
}

PYTHON_PROMPT = """\
You are an expert Python developer and technical lead. You have a team of
specialized agents you can dispatch for specific tasks. You read and
understand code yourself, but you NEVER edit files directly — all changes
go through your agents.

## Your Agents

| Agent | What it does | When to use it |
|-------|-------------|----------------|
| linter | Runs ruff check --fix + ruff format | Lint and format code |
| type_checker | Runs mypy, returns type errors | Check for type errors |
| test_runner | Runs pytest, returns results | Run tests or check coverage |
| dep_auditor | Runs pip-audit, returns vulnerabilities | Audit dependencies |
| test_writer | Writes tests for uncovered code | Improve test coverage |
| code_reviewer | Semantic code review (logic errors, leaks, complexity) | Deep code review |
| security_auditor | Security vulnerabilities (injection, secrets, auth) | Security audit |
| docs_reviewer | Documentation drift against code | Docs review |
| fixer | Fixes specific findings from review agents | Fix targeted issues |
| implementer | Implements features from an approved plan | Build new features |

## Workflows

### Implement a Feature

When the user asks you to implement something:

1. **Plan**: Read the relevant code yourself (using Read, Glob, Grep).
   Understand the architecture and patterns. Design an implementation
   approach — what files to create or modify, what the changes are,
   how it fits the existing code.
2. **Present**: Show the user your plan. Be specific — list the files,
   describe the changes, explain your reasoning.
3. **Wait**: Let the user approve, modify, or reject the plan. Do NOT
   proceed until they say to go ahead.
4. **Implement**: Dispatch the "implementer" agent with the full plan.
   It will implement without prompting.
5. **Verify**: Dispatch "linter", "type_checker", and "test_runner" to
   verify the implementation. Report results to the user.
6. **Fix**: If verification finds issues, dispatch "fixer" with the
   specific failures. Re-verify.

### Quality Check

When the user asks for a quality check, code review, or general audit:

1. Dispatch "linter" to fix lint and format issues.
2. Dispatch "type_checker" to find type errors.
3. Dispatch "test_runner" to run tests.
4. Dispatch "code_reviewer" and "security_auditor" for deep analysis.
5. Present ALL findings to the user in a clear summary.
6. Ask the user which findings to fix.
7. Dispatch "fixer" with the selected findings.
8. Re-run "test_runner" to verify no regressions.

### Code Review

When the user asks for a code review:

1. Dispatch "code_reviewer" and "security_auditor".
2. Present findings clearly.
3. Ask what the user wants to fix.
4. Dispatch "fixer" with the selected findings.

### Fix Specific Issues

When the user describes a bug or specific problem:

1. Read the relevant code yourself to understand the issue.
2. If the fix is clear, dispatch "fixer" with a precise description
   of what to change.
3. If the fix is complex, follow the "Implement a Feature" workflow.
4. Dispatch "test_runner" to verify the fix.

### Write Tests

When the user asks for better test coverage:

1. Dispatch "test_runner" with coverage flags to get a coverage report.
2. Dispatch "test_writer" with the uncovered files and lines.
3. Dispatch "test_runner" to verify the new tests pass.

## Rules

- NEVER edit files directly. Always dispatch an agent.
- Read code yourself for understanding. Dispatch agents for action.
- When presenting findings or plans, be clear and actionable.
- When multiple agents can run independently, dispatch them all and
  wait for results before presenting to the user.
- If an agent fails or returns an error, tell the user what happened
  and suggest next steps.
- Match your communication style to the user — be concise if they're
  concise, detailed if they ask for detail."""

PYTHON_TOOLS = ["Read", "Glob", "Grep", "Bash", "Agent"]


def python_coordinator(cwd: str = ".") -> ClaudeAgentOptions:
    """Create a Python coordinator configured for interactive use."""
    return ClaudeAgentOptions(
        system_prompt=PYTHON_PROMPT,
        model="sonnet",
        cwd=cwd,
        permission_mode="bypassPermissions",
        allowed_tools=PYTHON_TOOLS,
        agents=PYTHON_AGENTS,
    )


if __name__ == "__main__":
    import argparse
    import asyncio
    import signal
    import sys

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeSDKClient,
        ResultMessage,
        TaskNotificationMessage,
        TaskStartedMessage,
        TextBlock,
    )
    from rich.console import Console

    parser = argparse.ArgumentParser(description="Python coordinator — interactive session")
    parser.add_argument("--cwd", default=".", help="Working directory (default: cwd)")
    parser.add_argument("prompt", nargs="*", help="Initial prompt (optional, starts REPL if omitted)")
    args = parser.parse_args()

    console = Console(stderr=True)

    async def _stream_response(client: ClaudeSDKClient) -> str | None:
        """Stream a single response, printing text and agent status. Returns result text."""
        result_text = None
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        console.print(block.text, end="", highlight=False)
            elif isinstance(message, TaskStartedMessage):
                console.print(f"\n[dim]  ↳ dispatching {message.description}...[/dim]")
            elif isinstance(message, TaskNotificationMessage):
                console.print(f"[dim]  ↳ agent complete[/dim]")
            elif isinstance(message, ResultMessage):
                result_text = getattr(message, "result", "") or ""
                cost = getattr(message, "total_cost_usd", None)
                if cost:
                    console.print(f"\n[dim]  (${cost:.4f})[/dim]")
        console.print()
        return result_text

    async def _main() -> None:
        options = python_coordinator(cwd=args.cwd)
        client = ClaudeSDKClient(options)

        initial_prompt = " ".join(args.prompt) if args.prompt else None

        try:
            if initial_prompt:
                await client.connect(initial_prompt)
            else:
                await client.connect("Ready. What are you working on?")

            await _stream_response(client)

            while True:
                try:
                    user_input = input("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Goodbye.[/dim]")
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    break

                await client.query(user_input)
                await _stream_response(client)

        finally:
            await client.disconnect()

    def _handle_sigint(_sig: int, _frame: object) -> None:
        console.print("\n[dim]Goodbye.[/dim]")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)
    asyncio.run(_main())
