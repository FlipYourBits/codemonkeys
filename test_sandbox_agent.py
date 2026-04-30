"""Interactive sandboxed agent for testing filesystem restrictions.

Usage:
    .venv/bin/python test_sandbox_agent.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from codemonkeys.sandbox import restrict


async def main() -> None:
    project = Path(__file__).resolve().parent
    print(f"Sandboxing writes to: {project}")
    restrict(project)
    print("Sandbox applied. All writes outside this directory will be denied.\n")

    options = ClaudeAgentOptions(
        system_prompt=(
            "You are a helpful assistant. You have full tool access — "
            "Read, Write, Edit, Bash, Glob, Grep. Do whatever the user asks. "
            "If a tool call fails with a permission error, report the exact error."
        ),
        model="haiku",
        cwd=str(project),
        permission_mode="acceptEdits",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    )

    client = ClaudeSDKClient(options)
    await client.connect("Greet the user. Mention you're sandboxed to the project directory.")

    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)
        elif isinstance(msg, ResultMessage):
            print()

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            break
        if not user_input:
            continue

        await client.query(user_input)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text, end="", flush=True)
            elif isinstance(msg, ResultMessage):
                print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
