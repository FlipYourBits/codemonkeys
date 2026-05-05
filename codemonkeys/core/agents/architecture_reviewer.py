"""Architecture reviewer — cross-file design analysis.

Dispatched once per review after per-file agents complete. Receives
structural metadata (from ast) and per-file summaries so it can
reason about cross-file design issues without reading source files.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import DESIGN_REVIEW


def make_architecture_reviewer(
    *,
    files: list[str],
    file_summaries: list[dict[str, str]],
    structural_metadata: str,
) -> AgentDefinition:
    """Create an architecture reviewer scoped to the given files.

    ``structural_metadata`` is pre-formatted text from ``format_analysis()``
    containing imports, function signatures, and class hierarchies extracted
    via ast.  The agent reasons over this metadata instead of reading files.
    """
    summaries_text = "\n".join(
        f"- `{s['file']}`: {s['summary']}" for s in file_summaries
    )

    return AgentDefinition(
        description="Cross-file architecture and design review",
        prompt=f"""\
You review a codebase for cross-file design issues. You have been given:

1. **Structural metadata** — imports, function signatures, class hierarchies,
   and decorators extracted via static analysis (ast). This is deterministic
   and complete.
2. **Per-file summaries** — one-sentence descriptions from per-file reviewers
   who already read the source code.

Use these to identify cross-file design problems. You should NOT need to read
source files — the metadata and summaries give you everything for design analysis.
If you need to verify a specific detail, you may read a single file, but do not
read all files.

## Structural Metadata

{structural_metadata}

## Per-File Summaries

{summaries_text}

## Method

1. Analyze the import graph for dependency direction, coupling, and cycles.
2. Compare function signatures and class interfaces across files for consistency.
3. Check whether files doing similar work use the same paradigm (async/sync,
   classes/functions, similar patterns).
4. Cross-reference summaries to find duplicated responsibilities or communication
   mismatches.
5. Report only genuine cross-file issues — per-file quality and security problems
   were already caught by per-file reviewers.

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
        tools=["Read"],
        permissionMode="dontAsk",
    )
