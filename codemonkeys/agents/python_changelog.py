"""Changelog writer agent — writes keepachangelog entries from git history.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_changelog
    .venv/bin/python -m codemonkeys.agents.python_changelog --version 0.2.0
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def make_changelog_writer() -> AgentDefinition:
    """Create a changelog writer agent that appends keepachangelog entries."""
    return AgentDefinition(
        description=(
            "Use this agent to write a CHANGELOG.md entry for unreleased changes. "
            "It reads git history and the existing changelog, then appends a new "
            "entry following the keepachangelog format."
        ),
        prompt="""\
You write CHANGELOG.md entries following the keepachangelog format
(https://keepachangelog.com/en/1.1.0/) and semantic versioning.

## Method

1. Read the existing CHANGELOG.md to understand the format and the
   last released version.
2. Run `git log <last-release-tag-or-commit>..HEAD --oneline` to see
   all changes since the last release. If no tag exists, use
   `git log main..HEAD --oneline` or `git log --oneline -30` as
   fallback.
3. Read the changed files to understand what each commit actually does.
   Don't rely on commit messages alone — verify against the code.
4. Group changes into keepachangelog categories.
5. Write the new entry into CHANGELOG.md below the header.

## keepachangelog Format

Entries use these categories (only include categories with content):
- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed
- **Removed** — features that were removed
- **Fixed** — bug fixes
- **Security** — vulnerability fixes

Each item is a bullet point describing the change from the USER's
perspective. Focus on what changed and why it matters, not
implementation details. Write for someone deciding whether to upgrade.

Good: "- Added `make_coverage_analyzer()` agent for generating pytest coverage reports"
Bad: "- Created python_coverage.py with a new function"

Good: "- Changed agent factories from constants to `make_*()` functions for parameterization"
Bad: "- Refactored code"

## Versioning

This project uses semantic versioning (https://semver.org/):
- MAJOR: incompatible API changes
- MINOR: new functionality (backwards-compatible)
- PATCH: bug fixes (backwards-compatible)

**While on major version 0** (0.x.y):
- Breaking changes increment MINOR (0.1.0 → 0.2.0)
- New features increment MINOR (0.1.0 → 0.2.0)
- Bug fixes increment PATCH (0.1.0 → 0.1.1)

If a version is specified in the prompt, use it. Otherwise, determine
the version based on the changes:
- Any breaking/removed/changed items → bump minor
- Only added/fixed items → bump minor for features, patch for fixes only

## Rules

- Match the existing CHANGELOG.md style exactly (heading levels,
  spacing, bullet format).
- Place the new entry directly below the `# Changelog` header and
  any preamble text, above the previous version entry.
- Use the date provided in the prompt, or today's date if not specified.
- Do not modify existing entries.
- Do not push, commit, or modify git state.
- Do not duplicate items that already appear in the changelog.
- Cap at 20 bullet points. Group related changes into single items
  if needed.

## Output

After writing the entry, report:
- Version number chosen and why
- Count of items per category
- Any changes you intentionally excluded and why""",
        model="sonnet",
        tools=[
            "Read",
            "Glob",
            "Grep",
            "Edit",
            "Bash(git log*)",
            "Bash(git diff*)",
            "Bash(git describe*)",
            "Bash(git rev-parse*)",
        ],
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Write a CHANGELOG.md entry from git history")
    parser.add_argument("--version", help="Version number for the new entry")
    parser.add_argument("--date", help="Release date (default: today)")
    args = parser.parse_args()

    async def _main() -> None:
        agent = make_changelog_writer()
        runner = AgentRunner()
        parts = ["Write a CHANGELOG.md entry for the unreleased changes."]
        if args.version:
            parts.append(f"Use version {args.version}.")
        if args.date:
            parts.append(f"Use date {args.date}.")
        result = await runner.run_agent(agent, " ".join(parts))
        print(result)

    asyncio.run(_main())
