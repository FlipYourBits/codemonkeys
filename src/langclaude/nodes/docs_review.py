"""Docs-review node: checks documentation for drift against the code.

Owns doc accuracy exclusively: stale docstrings, outdated READMEs,
missing public-API docs, inconsistent terminology. Does NOT check
code quality, security, tests, or formatting — other nodes own those.

When Edit/Write are in the allow list, the agent also fixes drifted docs.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SKILL = """\

# Docs review

You are reviewing documentation for drift against the code it describes. Focus on **accuracy**, not style or tone. Confidence floor is 0.85.

## Scope

- **Diff mode**: review docs touched by the diff *and* code changes that may have invalidated docs elsewhere. Use `git diff BASE_REF...HEAD` to see what changed.
- **Full mode**: review every public-API docstring and every README reference.

## What to look for

### `docstring_drift`
- Docstring describes parameters, return values, or exceptions that don't match the current signature
- Examples in the docstring use removed APIs or pre-rename names
- Docstring claims behavior that the implementation no longer does (e.g. "raises ValueError" but the function now returns None on the same input)

### `readme_drift`
- README references a function, class, or file that has been renamed or deleted
- Code blocks in the README import or call symbols that no longer exist
- "Quick start" snippet uses a deprecated API

### `missing_public_docstring`
- A new public function/class/method (no leading underscore, exported in `__all__` or visible at package root) has no docstring or only a one-line stub
- A new public CLI command or HTTP endpoint with no documentation

### `stale_changelog`
- CHANGELOG.md / release notes don't reflect a public-API change in the diff
- Version bumped without a corresponding changelog entry (only flag if the project clearly maintains a changelog)

### `inconsistent_terminology`
- The same concept is named differently across docs and code (e.g. README says "API key", code uses `auth_token`) — only flag when the divergence would confuse a reader

## Exclusions — DO NOT REPORT

- Style preferences (tone, length, formatting)
- Typos and grammar (a separate pass)
- Internal/private implementation details
- Comments in code (that's the code reviewer's job)
- Wishlist items: "this could use more examples"
- Pre-existing drift outside the diff (in diff mode)

## Method

1. Read the diff to find changed signatures, renamed/removed symbols, new public APIs.
2. For each changed signature: locate the docstring (if any) and check it still matches.
3. For each renamed/removed symbol: grep the README and `docs/` for references to the old name.
4. For each new public API: confirm it has a real docstring.
5. Triage: drop anything below 0.85 confidence.

## Output

A single fenced JSON block, schema-compatible with the other review nodes. Final reply must be the JSON and nothing after it.

```json
{
  "mode": "diff" | "full",
  "findings": [
    {
      "file": "src/foo.py",
      "line": 10,
      "severity": "MEDIUM",
      "category": "docstring_drift",
      "source": "docs-review",
      "description": "Docstring says raises ValueError but function returns None on bad input.",
      "recommendation": "Update the docstring to match the current behavior.",
      "confidence": 0.92
    }
  ],
  "summary": {
    "files_reviewed": 5,
    "high": 0,
    "medium": 2,
    "low": 0
  }
}
```

Severity guide:
- **HIGH**: doc actively misleads (wrong return type, wrong exceptions, broken example)
- **MEDIUM**: doc out of date but unlikely to cause immediate user error
- **LOW**: minor stale reference

If there are no findings, return an empty `findings` array."""

_REVIEW_ONLY_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the skill below exactly. "
    "Do not edit files; do not push. Output JSON only as your final message." + _SKILL
)

_REVIEW_AND_FIX_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the skill below exactly. "
    "After reviewing, update any docs that have drifted — fix factual "
    "errors, update outdated examples, add missing sections. Do not push. "
    "Output JSON only as your final message." + _SKILL
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_docs_review_node(
    *,
    name: str = "docs_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "docs_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a docs-review node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``docs_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(
            _READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY
        )

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only doc drift introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` and "
            "reading any doc files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        ) % (base_ref_key, base_ref_key)
    else:
        prompt_template = (
            "FULL mode — review docs in the repository at "
            "{working_dir}. Start by listing files and reading any doc "
            "files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
