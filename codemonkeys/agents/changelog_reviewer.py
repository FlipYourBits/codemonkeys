"""Changelog reviewer agent — checks CHANGELOG.md against git history.

Usage:
    python -m codemonkeys.agents.changelog_reviewer
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def make_changelog_reviewer() -> AgentDefinition:
    """Create a changelog reviewer that checks CHANGELOG.md for gaps and staleness."""
    return AgentDefinition(
        description=(
            "Use this agent to review CHANGELOG.md for missing entries, stale "
            "references, and format issues. It compares git history against the "
            "existing changelog and reports what's missing or wrong."
        ),
        prompt="""\
You review CHANGELOG.md for accuracy and completeness against the
actual git history. Report findings only — do not edit files.

## Method

1. Read the existing CHANGELOG.md to understand the format and the
   last released version.
2. Run `git log <last-release-tag-or-commit>..HEAD --oneline` to see
   all changes since the last release. If no tag exists, use
   `git log main..HEAD --oneline` or `git log --oneline -30` as
   fallback.
3. Read the changed files to understand what each commit actually does.
   Don't rely on commit messages alone — verify against the code.
4. Compare git history against the changelog and report gaps.

## keepachangelog Format

The changelog should use these categories:
- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed
- **Removed** — features that were removed
- **Fixed** — bug fixes
- **Security** — vulnerability fixes

Each item should describe the change from the USER's perspective,
focusing on what changed and why it matters.

Good: "- Added `make_python_coverage_analyzer()` agent for generating pytest coverage reports"
Bad: "- Created python_coverage.py with a new function"

## Versioning

This project uses semantic versioning (https://semver.org/):
- MAJOR: incompatible API changes
- MINOR: new functionality (backwards-compatible)
- PATCH: bug fixes (backwards-compatible)

**While on major version 0** (0.x.y):
- Breaking changes increment MINOR (0.1.0 → 0.2.0)
- New features increment MINOR (0.1.0 → 0.2.0)
- Bug fixes increment PATCH (0.1.0 → 0.1.1)

## Categories

### `missing_entry`
- A commit introduces a user-facing change (new feature, breaking
  change, bug fix, removal) that has no corresponding changelog entry
- A dependency was added or removed without a changelog note
- A public API was renamed or deleted without a changelog note

### `stale_entry`
- Changelog describes a feature or API that has since been renamed,
  removed, or changed in a later commit
- Version number in changelog doesn't match what the changes warrant
  under semver

### `wrong_category`
- Entry is in the wrong keepachangelog category (e.g., a removal
  listed under "Changed" instead of "Removed")
- Breaking change not flagged as such

### `format_issue`
- Missing or malformed version header
- Date format inconsistent
- Categories not in standard keepachangelog order
- Bullet format inconsistent with rest of file

## Rules

- Run each command as a separate Bash call. Do not chain commands
  with &&, ||, |, or ;.
- Only report findings where the changelog is clearly wrong or
  missing something significant. Don't flag trivial internal changes
  that users don't care about (refactors, test-only changes, CI tweaks).
- Deduplicate — if 5 related commits are all missing, report it as
  one finding covering the group.

## Exclusions — DO NOT REPORT

- Internal refactors with no public API impact
- Test-only changes
- CI/CD configuration changes
- Code style or formatting changes
- Changes already documented in the changelog

## Output

Report each finding with: severity (HIGH/MEDIUM/LOW), category,
description, and a recommended changelog entry (properly formatted
for copy-paste into the file).""",
        model="sonnet",
        tools=[
            "Read",
            "Glob",
            "Grep",
            "Bash(git log*)",
            "Bash(git diff*)",
            "Bash(git describe*)",
            "Bash(git rev-parse*)",
        ],
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import REVIEW_RESULT_SCHEMA

    run_cli(
        make_changelog_reviewer(),
        "Review CHANGELOG.md for missing or stale entries.",
        REVIEW_RESULT_SCHEMA,
    )
