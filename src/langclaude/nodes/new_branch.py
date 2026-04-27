"""Branch-namer node: generates a branch name, handles dirty-tree safety,
and creates + switches to the new branch.

Modes
-----
- "interactive"  show the proposed name, let the user accept/rename/abort.
                 If the working tree is dirty, prompt: stash / commit / carry.
                 Falls back to "auto" when stdin isn't a TTY.
- "auto"         accept the first generated name, carry uncommitted changes.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import HAIKU_4_5
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["interactive", "auto"]

AskBranchName = Callable[[str], Awaitable[tuple[str, str]]]
AskDirtyTree = Callable[[str], Awaitable[str]]

_SYSTEM_PROMPT = """\
You generate git branch names. \
Read the user's task description and reply with ONE branch name on a single \
line. No quotes, no markdown, no explanation, no trailing punctuation. \
Follow the git guidelines below.

## Operating guidelines

# Git branch and commit guidelines

## Branch names

Use the format `<type>/<kebab-case-summary>`. Keep summaries short (3–6 words), lowercase, hyphen-separated. No spaces, no underscores, no slashes inside the summary.

Types:

- `feat/` — new feature or capability
- `fix/` — bug fix
- `chore/` — tooling, config, dependency bumps, build changes
- `refactor/` — internal restructuring with no behavior change
- `docs/` — documentation only
- `test/` — adding or fixing tests
- `perf/` — performance improvement
- `ci/` — CI/CD pipeline changes

Examples of good branch names:

- `feat/oauth-google-login`
- `fix/null-pointer-on-empty-cart`
- `refactor/extract-payment-service`
- `chore/bump-pydantic-to-2`
- `docs/add-api-quickstart`

Avoid:

- Personal prefixes (`john/...`) unless the team convention requires them
- Ticket IDs alone (`PROJ-1234`) — include a human-readable summary too
- Vague summaries (`feat/updates`, `fix/bug`)
- Branch names over ~50 characters

## Commit messages

Subject line: imperative mood, ≤72 characters, no trailing period.

- Good: `Fix race condition in worker shutdown`
- Bad:  `fixed bug` / `Updated some files.`

Body (when needed): wrap at 72, explain *why* the change was made, what alternatives were considered, and any non-obvious constraints. The diff already shows *what* changed.

When asked to generate ONLY a branch name, reply with just the branch name on a single line — no quotes, no explanation, no markdown."""

_PROMPT_TEMPLATE = (
    "Generate a git branch name for the following task:\n\n{task_description}"
)


def _run(argv: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _is_dirty(cwd: str) -> bool:
    result = _run(["git", "status", "--porcelain"], cwd)
    return bool(result.stdout.strip())


def _git_status_summary(cwd: str) -> str:
    result = _run(["git", "status", "--short"], cwd)
    return result.stdout.strip()


async def ask_branch_name_via_stdin(proposed: str) -> tuple[str, str]:
    """Prompt user to accept, rename, or abort.

    Returns (action, branch_name) where action is 'accept', 'rename', or 'abort'.
    """
    if not sys.stdin.isatty():
        return ("accept", proposed)
    prompt = (
        f"\n[langclaude] Proposed branch: {proposed}\n  [y]es / [r]ename / [a]bort: "
    )
    answer = await asyncio.to_thread(input, prompt)
    a = answer.strip().lower()[:1]
    if a == "r":
        new_name = await asyncio.to_thread(input, "  New branch name: ")
        return ("rename", new_name.strip())
    if a == "a":
        return ("abort", proposed)
    return ("accept", proposed)


async def ask_dirty_tree_via_stdin(status: str) -> str:
    """Prompt user about uncommitted changes.

    Returns 'stash', 'commit', 'carry', or 'abort'.
    """
    if not sys.stdin.isatty():
        return "carry"
    prompt = (
        f"\n[langclaude] Uncommitted changes detected:\n"
        f"{status}\n\n"
        f"  [s]tash / [c]ommit / [b]ring changes / [a]bort: "
    )
    answer = await asyncio.to_thread(input, prompt)
    a = answer.strip().lower()[:1]
    if a == "s":
        return "stash"
    if a == "c":
        msg = await asyncio.to_thread(input, "  Commit message: ")
        return f"commit:{msg.strip()}"
    if a == "a":
        return "abort"
    return "carry"


def claude_new_branch_node(
    *,
    name: str = "branch_namer",
    mode: Mode = "interactive",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] = (),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = HAIKU_4_5,
    max_turns: int = 1,
    output_key: str = "branch_name",
    verbose: bool = False,
    ask_name: AskBranchName = ask_branch_name_via_stdin,
    ask_dirty: AskDirtyTree = ask_dirty_tree_via_stdin,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a node that generates a branch name, handles dirty trees,
    and creates + switches to the new branch.

    State input:
        working_dir: repo root.
        task_description: used to generate the branch name.

    State output:
        branch_name: the final branch name.

    Args:
        mode: "interactive" prompts for approval and dirty-tree handling.
            "auto" accepts the name and carries uncommitted changes.
            Interactive falls back to auto when stdin isn't a TTY.
        ask_name: async callback for branch name approval.
        ask_dirty: async callback for dirty-tree handling.
    """
    allow_list = list(allow) if allow is not None else []
    namer = ClaudeAgentNode(
        name=f"{name}_inner",
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=allow_list,
        deny=list(deny),
        prompt_template=_PROMPT_TEMPLATE,
        output_key=output_key,
        on_unmatched=on_unmatched,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get("working_dir") or "."
        effective: Mode = mode
        if mode == "interactive" and not sys.stdin.isatty():
            effective = "auto"

        result = await namer(state)
        proposed = result[output_key].strip()

        if effective == "interactive":
            action, branch_name = await ask_name(proposed)
            if action == "abort":
                raise RuntimeError("Branch creation aborted by user")
            if action == "rename":
                proposed = branch_name
        branch_name = proposed

        dirty = await asyncio.to_thread(_is_dirty, cwd)
        if dirty:
            if effective == "interactive":
                status = await asyncio.to_thread(_git_status_summary, cwd)
                choice = await ask_dirty(status)
                if choice == "abort":
                    raise RuntimeError("Branch creation aborted by user")
                if choice == "stash":
                    await asyncio.to_thread(
                        lambda: _run(["git", "stash", "--include-untracked"], cwd)
                    )
                elif choice.startswith("commit:"):
                    msg = choice[len("commit:") :]
                    await asyncio.to_thread(
                        lambda: (
                            _run(["git", "add", "-A"], cwd),
                            _run(["git", "commit", "-m", msg or "WIP"], cwd),
                        )
                    )
            # auto mode: carry changes (do nothing)

        proc = await asyncio.to_thread(
            lambda: _run(["git", "checkout", "-b", branch_name], cwd)
        )
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode,
                ["git", "checkout", "-b", branch_name],
                output=proc.stdout,
                stderr=proc.stderr,
            )

        return {output_key: branch_name}

    run.__name__ = name
    run.declared_outputs = (output_key,)  # type: ignore[attr-defined]
    return run
