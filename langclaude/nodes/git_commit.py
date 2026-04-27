"""Git commit node: stages and commits changes, optionally pushes.

The agent reviews uncommitted changes, writes a conventional commit
message, stages, and commits. Then the user is asked whether to push.
Falls back to auto-approve (commit + push) when stdin isn't a TTY.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.display import default_prompt as _default_prompt
from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

AskPush = Callable[[str], Awaitable[Literal["push", "skip", "feedback"] | str]]
PromptFn = Callable[[str, str | None], str]

_SYSTEM_PROMPT = (
    "You commit code changes. "
    "Run `git diff --cached` and `git diff` to understand what changed, "
    "then write a clear conventional commit message summarizing the work. "
    "Stage all changes and commit. Do NOT push — that is a separate step. "
    "Reply with the commit hash and a short summary of what was committed."
)

_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Bash(git add*)",
    "Bash(git commit*)",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]

_DENY = [
    "Bash(git rebase*)",
    "Bash(git reset --hard*)",
    "Bash(git push*)",
    "Edit",
    "Write",
]


async def ask_push_via_stdin(
    summary: str,
    prompt_fn: PromptFn | None = None,
) -> Literal["push", "skip", "feedback"] | str:
    if not sys.stdin.isatty():
        return "push"
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(prompt, "[git_commit] (p)ush / (s)kip push / or provide feedback:", summary)
    a = answer.strip()
    if a.lower() in ("p", "push", "y", "yes", ""):
        return "push"
    if a.lower() in ("s", "skip", "n", "no"):
        return "skip"
    return a


def _push(cwd: str) -> str:
    result = subprocess.run(
        ["git", "push", "--set-upstream", "origin", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"push failed: {result.stderr.strip()}"
    return result.stderr.strip() or result.stdout.strip()


def git_commit_node(
    *,
    name: str = "git_commit",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_push: AskPush = ask_push_via_stdin,
    prompt_fn: PromptFn | None = None,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    if prompt_fn is not None and ask_push is ask_push_via_stdin:
        from functools import partial
        ask_push = partial(ask_push_via_stdin, prompt_fn=prompt_fn)

    inner_name = f"{name}_inner"
    committer = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template="{_commit_prompt}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get("working_dir") or "."
        initial_prompt = (
            f"Review all uncommitted changes in {cwd}, "
            f"write a conventional commit message that summarizes the work, "
            f"then stage and commit."
        )

        prompt = initial_prompt
        total_cost = 0.0
        while True:
            result = await committer({**state, "_commit_prompt": prompt})
            summary = result[inner_name]
            total_cost += result.get("last_cost_usd", 0.0)

            choice = await ask_push(summary)

            if choice == "push":
                push_output = await asyncio.to_thread(_push, cwd)
                return {
                    name: f"{summary}\n\n{push_output}",
                    "last_cost_usd": total_cost,
                }

            if choice == "skip":
                return {name: summary, "last_cost_usd": total_cost}

            prompt = (
                f"You just committed. The user has feedback:\n\n{choice}\n\n"
                f"Amend or fix as needed (use `git commit --amend` if appropriate)."
            )

    run.__name__ = name
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
