"""AgentDefinition review workflow — dispatches the reviewer agent.

Usage:
    .venv/bin/python -m codemonkeys.workflows.prompt_review codemonkeys/agents/python_code_review.py
"""

from __future__ import annotations

import argparse
import asyncio

from claude_agent_sdk import ClaudeAgentOptions

from codemonkeys.agents import DEFINITION_REVIEWER
from codemonkeys.runner import AgentRunner


COORDINATOR_PROMPT = """\
You are an AgentDefinition reviewer. You have one agent: "reviewer".

Your job:
1. Dispatch the reviewer agent with the file path to analyze.
2. Return the reviewer's full output verbatim — do not summarize or edit it."""


async def main(file_path: str) -> None:
    options = ClaudeAgentOptions(
        system_prompt=COORDINATOR_PROMPT,
        model="opus",
        cwd=".",
        permission_mode="bypassPermissions",
        allowed_tools=["Agent"],
        agents={"reviewer": DEFINITION_REVIEWER},
    )

    runner = AgentRunner()
    result = await runner.run(
        options,
        f"Review the AgentDefinition in this file: {file_path}",
    )
    print(result or "No output from reviewer.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review an AgentDefinition for correctness")
    parser.add_argument("file", help="Path to the agent file to review")
    args = parser.parse_args()
    asyncio.run(main(args.file))
