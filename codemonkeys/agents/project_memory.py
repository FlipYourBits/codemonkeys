"""Project memory agent — maintains docs/codemonkeys/architecture.md.

Builds and maintains a comprehensive project understanding document.
Full scan on first run, incremental updates from git diff on subsequent runs.

Usage:
    python -m codemonkeys.agents.project_memory
    python -m codemonkeys.agents.project_memory --mode incremental --diff-from abc123
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

_ARCHITECTURE_SECTIONS = """\
Write `docs/codemonkeys/architecture.md` with these sections:

### 1. Project Overview
- What the project is, what problem it solves, who it's for
- Tech stack (language, framework, key dependencies from the project metadata)
- How to install and run it

### 2. Architecture
- Module-level map: what each top-level directory and package does
- Inter-module dependencies: which modules import from which
- Key data flows: how data moves through the system end-to-end

### 3. File Index
- One line per source file and test file: `path — what it does`
- Group by directory
- Skip `__pycache__/`, `.pyc`, and generated files

### 4. Key Abstractions
- The core concepts in the codebase: what they are, how they relate
- Use concrete names from the code (class names, function names)

### 5. Conventions
- Patterns the codebase follows (naming, file organization, code style)
- How to extend the project (e.g., how to add a new component following existing patterns)"""

_CONSTRAINTS = """\
## Constraints

- Only write files inside `docs/codemonkeys/`. Never modify source code.
- Describe what IS, not what SHOULD BE. No recommendations or suggestions.
- Keep `architecture.md` under 500 lines.
- After writing `architecture.md`, write the current HEAD commit SHA to
  `docs/codemonkeys/.memory-hash` (one line, no trailing newline).
  Get the SHA by running `git rev-parse HEAD`."""


_TOOLS = [
    "Write",
    "Bash(git log*)",
    "Bash(git diff*)",
    "Bash(git ls-files*)",
    "Bash(git rev-parse*)",
    "Bash(cat *)",
]


def _make_definition(description: str, prompt: str) -> AgentDefinition:
    return AgentDefinition(
        description=description,
        prompt=prompt,
        model="sonnet",
        tools=_TOOLS,
        permissionMode="dontAsk",
    )


def make_project_memory_agent(
    mode: Literal["full", "incremental"] = "full",
    diff_text: str | None = None,
) -> AgentDefinition:
    """Create a project memory agent that builds or updates architecture.md."""
    if mode == "incremental" and not diff_text:
        msg = "diff_text is required for incremental mode"
        raise ValueError(msg)

    if mode == "full":
        method = """\
## Method

1. Dump all tracked source files in a single command:
   `git ls-files | xargs cat`
   This gives you every file's contents in one pass — do NOT read
   files individually with Read or separate cat calls.
2. Write `docs/codemonkeys/architecture.md` from scratch with all
   five sections described below.
3. Write the current HEAD SHA to `docs/codemonkeys/.memory-hash`."""
    else:
        method = f"""\
## Method

1. Run `cat docs/codemonkeys/architecture.md` to read the current doc.
2. Review the diff below to understand what changed.
3. Read any new or significantly changed files referenced in the diff
   using `cat` (NOT individual Read calls).
4. Rewrite `docs/codemonkeys/architecture.md` in full, incorporating
   the changes. Do not patch sections — rewrite the entire document
   so all sections stay consistent with each other.
5. Write the current HEAD SHA to `docs/codemonkeys/.memory-hash`.

## Diff

```
{diff_text}
```"""

    return _make_definition(
        description=(
            "Use this agent to build or update the project memory document "
            "(docs/codemonkeys/architecture.md). It scans the codebase and "
            "writes a comprehensive architecture overview. Give it mode='full' "
            "for first-time scan or mode='incremental' with a git diff."
        ),
        prompt=f"""\
You build and maintain a project memory document that gives a
comprehensive understanding of the codebase.

{method}

## Sections

{_ARCHITECTURE_SECTIONS}

{_CONSTRAINTS}""",
    )


def make_project_memory_updater() -> AgentDefinition:
    """Create a self-contained project memory agent that checks staleness and updates."""
    return _make_definition(
        description=(
            "Checks if docs/codemonkeys/architecture.md is up to date with the "
            "current HEAD commit. If stale or missing, rebuilds or incrementally "
            "updates it. Safe to dispatch on startup — exits quickly if already fresh."
        ),
        prompt=f"""\
You build and maintain a project memory document that gives a
comprehensive understanding of the codebase.

## Method

1. Run `git rev-parse HEAD` to get the current commit SHA.
2. Run `cat docs/codemonkeys/.memory-hash` to check the stored hash.
   If the file doesn't exist, skip to step 5.
3. If the hash matches HEAD, respond "Project memory is up to date." and stop.
4. If the hash file exists but differs from HEAD:
   a. Run `git diff <stored_hash>..HEAD` to get the diff.
   b. Run `cat docs/codemonkeys/architecture.md` to read the current doc.
   c. Rewrite it in full, incorporating the changes from the diff.
      Read any changed files using `cat` (NOT individual Read calls).
      Do not patch sections — rewrite the entire document so all
      sections stay consistent with each other.
5. If the hash file does not exist (first run):
   a. Dump all tracked source files in a single command:
      `git ls-files | xargs cat`
      This gives you every file's contents in one pass — do NOT read
      files individually with Read or separate cat calls.
   b. Write `docs/codemonkeys/architecture.md` from scratch.
6. After writing architecture.md, write the HEAD SHA to
   `docs/codemonkeys/.memory-hash` (one line, no trailing newline).

## Sections

{_ARCHITECTURE_SECTIONS}

{_CONSTRAINTS}""",
    )


if __name__ == "__main__":
    import argparse
    import subprocess

    from codemonkeys.runner import run_cli

    parser = argparse.ArgumentParser(description="Build or update project memory")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full")
    parser.add_argument(
        "--diff-from", help="Commit SHA to diff from (for incremental mode)"
    )
    args = parser.parse_args()

    diff: str | None = None
    if args.mode == "incremental":
        if not args.diff_from:
            parser.error("--diff-from is required for incremental mode")
        diff = subprocess.check_output(
            ["git", "diff", f"{args.diff_from}..HEAD"],
        ).decode()

    agent = make_project_memory_agent(mode=args.mode, diff_text=diff)
    prompt = (
        "Build the project memory document from scratch."
        if args.mode == "full"
        else "Update the project memory document based on the diff."
    )
    run_cli(agent, prompt)
