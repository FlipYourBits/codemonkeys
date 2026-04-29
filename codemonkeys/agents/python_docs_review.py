"""Docs review agent — finds documentation drift against code.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_docs_review
    .venv/bin/python -m codemonkeys.agents.python_docs_review --scope repo
    .venv/bin/python -m codemonkeys.agents.python_docs_review --scope diff --path src/
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition


def make_docs_reviewer(
    scope: Literal["diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    if scope == "diff":
        if path:
            step_one = (
                f"Read the diff (`git diff main...HEAD -- '{path}'`) to find "
                "changed signatures, renamed/removed symbols, new public APIs."
            )
            start_by = (
                f"Start by running `git diff main...HEAD -- '{path}'` and reading "
                "any doc files (README, CHANGELOG, etc.)."
            )
        else:
            step_one = (
                "Read the diff to find changed signatures, renamed/removed symbols, "
                "new public APIs."
            )
            start_by = (
                "Start by running `git diff main...HEAD` and reading any doc files "
                "(README, CHANGELOG, etc.). If no diff, run `git ls-files` to find "
                "doc files and Python source files."
            )
        scope_exclusion = "\n- Pre-existing drift outside the diff"
    else:
        if path:
            step_one = (
                f"Read all Python source files under `{path}` to identify public "
                "signatures, symbols, and APIs."
            )
            start_by = (
                f"Find all Python and doc files under `{path}` using "
                f"`git ls-files '{path}'`."
            )
        else:
            step_one = (
                "Read all Python source files to identify public signatures, "
                "symbols, and APIs."
            )
            start_by = (
                "Run `git ls-files` to find all Python source files and doc files "
                "(README, CHANGELOG, etc.)."
            )
        scope_exclusion = ""

    return AgentDefinition(
        description=(
            "Use this agent to review documentation for drift against the code it "
            "describes: stale docstrings, broken README examples, missing public API docs."
        ),
        prompt=f"""\
Review documentation for drift against the code it describes. Focus on
accuracy, not style or tone.

Report findings only — do not fix issues.

## Method

1. {step_one}
2. For each changed signature: locate the docstring (if any) and check
   it still matches.
3. For each renamed/removed symbol: grep the README and `docs/` for
   references to the old name.
4. For each new public API: confirm it has a real docstring.
5. Check install/setup instructions and project metadata (pyproject.toml)
   against the current code.
6. Triage: drop anything you're not sure is actually wrong. If the doc
   is arguably still correct, leave it.

{start_by}

## Categories

### `docstring_drift`
- Docstring describes parameters, return values, or exceptions that
  don't match the current signature
- Examples in the docstring use removed APIs or pre-rename names
- Docstring claims behavior that the implementation no longer does
  (e.g., "raises ValueError" but the function now returns None)

### `doc_drift`
- README or docs/ reference a function, class, file, or CLI command that
  has been renamed or deleted
- Code blocks in docs import or call symbols that no longer exist
- Install/quick-start snippet uses a wrong package name, removed
  dependency, or deprecated API
- Documented CLI flags, env vars, or config options no longer exist
- CLI --help descriptions don't match what is documented

### `missing_public_docstring`
- A new public function/class/method (no leading underscore, exported in
  `__all__` or visible at package root) has no docstring or only a
  one-line stub

### `stale_changelog`
- CHANGELOG.md / release notes don't reflect a public-API change
- Version bumped without a corresponding changelog entry
- Changelog entry describes a change that doesn't match what happened

### `inconsistent_terminology`
- The same concept is named differently across docs and code (e.g.
  README says "API key", code uses `auth_token`) — only flag when the
  divergence would confuse a reader

## Triage

- Only report findings where the doc is clearly wrong. If arguably still
  correct, leave it out.
- Deduplicate — if the same rename broke 5 references, report it once.

## Exclusions — DO NOT REPORT

- Style preferences (tone, length, formatting)
- Typos and grammar
- Internal/private implementation details
- Comments in code (code review owns these)
- Wishlist items ("this could use more examples")
- Suggestions for documentation that doesn't exist yet{scope_exclusion}

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category, description, recommendation.""",
        model="sonnet",
        tools=["Read", "Glob", "Grep", "Bash"],
        disallowedTools=[
            "Bash(git push*)",
            "Bash(git commit*)",
            "Bash(pip install*)",
            "Bash(pip uninstall*)",
        ],
        permissionMode="dontAsk",
    )


DOCS_REVIEWER = make_docs_reviewer()


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Docs review — documentation drift against code")
    parser.add_argument("--scope", choices=["diff", "repo"], default="diff")
    parser.add_argument("--path", help="Narrow scope to this file or folder")
    args = parser.parse_args()

    async def _main() -> None:
        agent = make_docs_reviewer(scope=args.scope, path=args.path)
        runner = AgentRunner()
        prompt = f"Review documentation for {args.path}." if args.path else "Review documentation for drift against the code."
        result = await runner.run_agent(agent, prompt)
        print(result)

    asyncio.run(_main())
