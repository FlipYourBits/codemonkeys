"""Prompt review coordinator — reviews and optionally rewrites agent prompts.

Usage:
    .venv/bin/python -m codemonkeys.coordinators.prompt_review codemonkeys/agents/python_code_review.py
"""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from codemonkeys.agents import PROMPT_REVIEWER


COORDINATOR_PROMPT = """\
You are a prompt quality reviewer. You have one agent: "reviewer".

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
    print(f"\n{'---' * 20}")

    match = re.search(r"```(?:python)?\s*\n(.*?)\n```", result_text, re.DOTALL)
    if not match:
        print("No revised prompt proposed — file looks comprehensive.")
        return

    revised = match.group(1)
    choice = input("\nApply revised prompt? [y/n]: ").strip().lower()
    if choice not in ("y", "yes"):
        print("No changes made.")
        return

    original = Path(file_path).read_text(encoding="utf-8")
    prompt_match = re.search(
        r'(    prompt="""\\\n)(.*?)(""",)',
        original,
        re.DOTALL,
    )
    if not prompt_match:
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
        out_path = file_path + ".revised"
        Path(out_path).write_text(revised, encoding="utf-8")
        print(f"Could not auto-apply. Revised prompt written to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review an agent prompt for comprehensiveness")
    parser.add_argument("file", help="Path to the agent file to review")
    args = parser.parse_args()
    asyncio.run(main(args.file))
