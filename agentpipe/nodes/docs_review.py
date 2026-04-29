"""Documentation drift review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentpipe.models import SONNET_4_6
from agentpipe.nodes.base import ClaudeAgentNode


class DocsReviewFinding(BaseModel):
    file: str = Field(examples=["src/foo.py"])
    line: int = Field(examples=[10])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: doc actively misleads (wrong return type, wrong exceptions, broken example, broken install instructions). MEDIUM: doc out of date but unlikely to cause immediate user error. LOW: minor stale reference."
    )
    category: str = Field(examples=["docstring_drift"])
    source: str = Field(examples=["docs_review"])
    description: str = Field(
        examples=["Docstring says raises ValueError but function returns None."]
    )
    recommendation: str = Field(
        examples=["Update the docstring to match the current behavior."]
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="high: confident this is wrong. medium: likely wrong but some ambiguity. low: speculative."
    )


class DocsReviewOutput(BaseModel):
    findings: list[DocsReviewFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"files_reviewed": 5, "high": 0, "medium": 2, "low": 0}],
    )


_SKILL = """\
# Docs review

Review documentation for drift against the code it
describes. Focus on **accuracy**, not style or tone.

Report findings only — do not fix issues.

## Scope

{scope_section}

## Method

{method_steps}

## Categories

### `docstring_drift`
- Docstring describes parameters, return values, or
  exceptions that don't match the current signature
- Examples in the docstring use removed APIs or
  pre-rename names
- Docstring claims behavior that the implementation no
  longer does (e.g. "raises ValueError" but the function
  now returns None on the same input)

### `doc_drift`
- README or docs/ reference a function, class, file, or
  CLI command that has been renamed or deleted
- Code blocks in docs import or call symbols that no
  longer exist
- Install/quick-start snippet uses a wrong package name,
  removed dependency, or deprecated API
- Documented CLI flags, env vars, or config options no
  longer exist in the code
- CLI `--help` descriptions or argparse flags don't match
  what is documented in README or docs/

### `missing_public_docstring`
- A new public function/class/method (no leading
  underscore, exported in `__all__` or visible at package
  root) has no docstring or only a one-line stub

### `stale_changelog`
- CHANGELOG.md / release notes don't reflect a
  public-API change in the diff
- Version bumped without a corresponding changelog entry
  (only flag if the project clearly maintains a changelog)
- Changelog entry describes a change that doesn't match
  what actually happened (e.g. "Added X" when X was
  renamed, not added)
- Changelog entries not following Keep a Changelog format
  (https://keepachangelog.com/en/1.1.0/): sections must
  use `## [version] - YYYY-MM-DD` headings with
  `### Added`, `### Changed`, `### Deprecated`,
  `### Removed`, `### Fixed`, `### Security` subsections.
  Unreleased changes go under `## [Unreleased]`.

### `inconsistent_terminology`
- The same concept is named differently across docs and
  code (e.g. README says "API key", code uses
  `auth_token`) — only flag when the divergence would
  confuse a reader

## Triage

- Only report findings where the doc is clearly wrong.
  If arguably still correct, leave it out.
- Deduplicate — if the same rename broke 5 references,
  report it once.

## Exclusions — DO NOT REPORT

- Style preferences (tone, length, formatting)
- Typos and grammar
- Internal/private implementation details
- Comments in code (code review owns these)
- Wishlist items ("this could use more examples")
- Suggestions for documentation that doesn't exist yet{exclusion_extra}
"""


class DocsReview(ClaudeAgentNode):
    def __init__(
        self,
        *,
        scope: Literal["diff", "full_repo"] = "diff",
        base_ref: str = "main",
        **kwargs,
    ) -> None:
        kwargs.setdefault("model", SONNET_4_6)

        if scope == "diff":
            scope_section = (
                "Diff mode: review docs touched by the diff *and* code\n"
                "changes that may have invalidated docs elsewhere."
            )
            method_steps = """\
1. Read the diff to find changed signatures,
   renamed/removed symbols, new public APIs.
2. For each changed signature: locate the docstring
   (if any) and check it still matches.
3. For each renamed/removed symbol: grep the README and
   `docs/` for references to the old name.
4. For each new public API: confirm it has a real
   docstring.
5. Check install/setup instructions and project metadata
   (pyproject.toml) against the current code.
6. Triage: drop anything you're not sure is actually
   wrong. If the doc is arguably still correct, leave it."""
            exclusion_extra = "\n- Pre-existing drift outside the diff"
            prompt = (
                f"Report only doc drift introduced by the diff against {base_ref}. "
                f"Start by running `git diff {base_ref}...HEAD` and reading any doc files "
                "(README, CHANGELOG, etc.)."
            )
        else:
            scope_section = (
                "Full repo: review all documentation in the repository\n"
                "against the current code."
            )
            method_steps = """\
1. List all doc files (README, CHANGELOG, `docs/`) and
   all Python source files.
2. For each public function/class/method: check that its
   docstring matches the current signature and behavior.
3. For each doc file: check that referenced symbols,
   file paths, and code examples still exist and work.
4. Check install/setup instructions and project metadata
   (pyproject.toml) against the current code.
5. Triage: drop anything you're not sure is actually
   wrong. If the doc is arguably still correct, leave it."""
            exclusion_extra = ""
            prompt = (
                "Review all documentation in the repository against the current code. "
                "Start by running `git ls-files` to find doc files and Python source files."
            )

        super().__init__(
            name="docs_review",
            output=DocsReviewOutput,
            system_prompt=_SKILL.format(
                scope_section=scope_section,
                method_steps=method_steps,
                exclusion_extra=exclusion_extra,
            ),
            prompt_template=prompt,
            allow=[
                "Read",
                "Glob",
                "Grep",
                "Bash(git diff*)",
                "Bash(git log*)",
                "Bash(git show*)",
                "Bash(git blame*)",
                "Bash(git status*)",
                "Bash(git ls-files*)",
            ],
            deny=[],
            on_unmatched="deny",
            **kwargs,
        )
