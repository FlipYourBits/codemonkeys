"""README reviewer — verifies README.md claims against the codebase.

Returns structured JSON findings. Has read access and git ls-files.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition


def make_readme_reviewer() -> AgentDefinition:
    """Create a readme reviewer that checks README accuracy against the codebase."""
    return AgentDefinition(
        description="Review README.md for accuracy against the codebase",
        prompt="""\
You review README.md for accuracy by verifying its claims against the
actual codebase. Report findings only — do not fix issues.

## Method

1. Read README.md and project metadata (`pyproject.toml`, `setup.cfg`, `package.json`, etc.).
2. For every concrete claim in the README:
   - Import paths: grep to verify they exist
   - CLI commands: grep for argument parser or command registration
   - Function/class names: grep to verify they exist
   - Config options: grep to verify they're used
   - Code examples: verify imports and function calls would work
3. Check for required sections: description, prerequisites, installation, quick start, usage, license.
4. Check for undocumented major features (public modules/commands not mentioned in README).

## Output Format

Return ONLY a JSON object:

```json
{
  "file": "README.md",
  "summary": "<one sentence about README state>",
  "findings": [
    {
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "readme",
      "subcategory": "<stale_reference|broken_example|missing_section|inaccurate_metadata|incomplete_docs|quality>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }
  ]
}
```

## Rules

- Deduplicate — if the same rename broke 5 references, report once
- If README.md doesn't exist, return a single finding: missing_section
- If the README is accurate, return an empty findings array""",
        model="sonnet",
        tools=["Read", "Glob", "Grep", "Bash(git ls-files*)"],
        permissionMode="dontAsk",
    )
