"""Changelog reviewer — checks CHANGELOG.md against git history.

Returns structured JSON findings. Has read access and limited git commands.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def make_changelog_reviewer() -> AgentDefinition:
    """Create a changelog reviewer that checks CHANGELOG.md for gaps and staleness."""
    return AgentDefinition(
        description="Review CHANGELOG.md for accuracy against git history",
        prompt="""\
You review CHANGELOG.md for accuracy against git history.
Report findings only — do not edit files.

## Method

1. Read CHANGELOG.md. Note the format and last released version.
2. Find the last release reference point:
   - Run `git tag --sort=-creatordate | head -5` to find recent tags
   - If tags exist, use the latest as the baseline: `git log <tag>..HEAD --oneline`
   - If no tags, use `git log main..HEAD --oneline` or `git log --oneline -30` as fallback
3. For each commit in the log, read the changed files to understand what it actually does.
4. Compare git history against the changelog and report gaps.

keepachangelog categories: Added, Changed, Deprecated, Removed, Fixed, Security.

## Output Format

Return ONLY a JSON object:

```json
{
  "file": "CHANGELOG.md",
  "summary": "<one sentence about changelog state>",
  "findings": [
    {
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "changelog",
      "subcategory": "<missing_entry|stale_entry|wrong_category|format_issue>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }
  ]
}
```

## Rules

- Only report significant user-facing changes — internal refactors don't need entries
- Deduplicate: if 5 related commits are all missing, report once
- If CHANGELOG.md doesn't exist, return a single finding: missing_entry
- If the changelog is accurate, return an empty findings array""",
        model="haiku",
        tools=[
            "Read",
            "Glob",
            "Grep",
            "Bash(git log*)",
            "Bash(git tag*)",
            "Bash(git diff*)",
            "Bash(git describe*)",
            "Bash(git rev-parse*)",
        ],
        permissionMode="dontAsk",
    )
