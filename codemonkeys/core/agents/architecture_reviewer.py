"""Architecture reviewer — cross-file design analysis.

Dispatched once per review after per-file agents complete. Receives file
summaries from per-file agents and reads all source files to find
cross-file design issues. Has read-only access to the project.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import DESIGN_REVIEW


def make_architecture_reviewer(
    *,
    files: list[str],
    file_summaries: list[dict[str, str]],
) -> AgentDefinition:
    """Create an architecture reviewer scoped to the given files."""
    summaries_text = "\n".join(
        f"- `{s['file']}`: {s['summary']}" for s in file_summaries
    )
    files_text = "\n".join(f"- `{f}`" for f in files)

    return AgentDefinition(
        description="Cross-file architecture and design review",
        prompt=f"""\
You review a codebase for cross-file design issues. You have already received
summaries from per-file reviewers. Now read the actual source files and look
for design problems that span multiple files.

## Files in Scope

{files_text}

## Per-File Summaries (from previous review phase)

{summaries_text}

## Method

1. Read every file listed above.
2. As you read, track: paradigms used, communication patterns, dependency
   directions, layer boundaries, interface signatures, and cross-cutting concerns.
3. After reading all files, compare your observations across files using the
   design review checklist below.
4. Report only genuine cross-file issues — not per-file quality or security
   problems (those were already caught by per-file reviewers).

## Compaction Resilience

If you notice your context is getting large, write your observations to memory:
- Write a `progress.json` listing which files you've read so far.
- Write an `architecture_notes.json` with your accumulated observations.
If you find these files already exist in memory when you start, you've been
through a compaction — read them back and continue from where you left off.

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping:

```json
{{
  "files_reviewed": ["path/to/file1.py", "path/to/file2.py"],
  "findings": [
    {{
      "files": ["path/to/file1.py", "path/to/file2.py"],
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "design",
      "subcategory": "<checklist heading>",
      "title": "<short description>",
      "description": "<detailed explanation of the cross-file issue>",
      "suggestion": "<how to fix it, or null>"
    }}
  ]
}}
```

## Rules

- Only report findings at 80%+ confidence
- `files` must list ALL files involved in the finding
- `subcategory` must match a checklist heading below
- If the codebase has no cross-file design issues, return an empty findings array
- Do NOT report per-file quality or security issues
- Do NOT report formatting or type errors

{DESIGN_REVIEW}""",
        model="opus",
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
