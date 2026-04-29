"""Resolve-findings node: fixes issues from upstream review nodes.

Non-interactive (default): auto-fixes all HIGH+ severity issues.
Interactive: presents a formatted summary and lets the user pick
which findings to fix.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentpipe.display import default_prompt as _default_prompt
from agentpipe.models import OPUS_4_6
from agentpipe.nodes.base import (
    ClaudeAgentNode,
    _node_name,
)
from agentpipe.permissions import UnmatchedPolicy

AskFindings = Callable[[str], Awaitable[str | None]]
PromptFn = Callable[[str, str | None], str]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ── Pydantic models ──────────────────────────────────────────────


class FixedItem(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    category: str = Field(examples=["logic_error"])
    source: str = Field(examples=["python_code_review"])
    description: str = Field(examples=["What was fixed, one sentence."])


class SkippedItem(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[10])
    category: str = Field(examples=["clarity"])
    source: str = Field(examples=["python_code_review"])
    reason: str = Field(examples=["False positive — the code is correct because..."])


class ResolveOutput(BaseModel):
    fixed: list[FixedItem] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────


def _extract_items_from_state(
    reads_from_keys: list[str], state: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in reads_from_keys:
        upstream = state.get(key)
        if upstream is None:
            continue
        data = upstream.model_dump()
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                for item in value:
                    if not item.get("source"):
                        item["source"] = key
                    items.append(item)
    items.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "LOW"), 99))
    return items


_SKILL = """\
# Resolve findings

You fix specific findings reported by upstream review nodes.
Each finding includes a file, line, category, and description.
Fix only what is listed — nothing else.

## Method

1. Read the finding's file and surrounding context.
2. Understand the root cause described in the finding.
3. Make the smallest correct change that resolves the issue.
4. Re-read the changed file to verify correctness.
5. After all fixes, run `python -m pytest -x -q --tb=short
   --no-header` to check for regressions.

## Rules

- One fix per finding. Do not refactor, clean up, or
  improve surrounding code.
- If a finding is a false positive (the code is actually
  correct), skip it and note why in your summary.
- Do not introduce new imports, abstractions, or helpers
  unless the fix requires it.
- Do not push, commit, or modify git state.
- Do not fix issues that are not in the findings list."""

_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
    "Bash(pytest*)",
    "Bash(python -m pytest*)",
    "Bash(python -m unittest*)",
]

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
    "Bash(git push*)",
    "Bash(git commit*)",
]


_SEVERITY_STYLES = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "dim",
}


def _format_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No findings from upstream nodes."
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    table = Table(show_header=True, expand=False, padding=(0, 1))
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Sev", width=8)
    table.add_column("Source", style="cyan")
    table.add_column("Location")
    table.add_column("Description", max_width=60)

    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "?")
        style = _SEVERITY_STYLES.get(sev, "")
        table.add_row(
            str(i),
            Text(sev, style=style),
            f.get("source", "?"),
            f"{f.get('file', '?')}:{f.get('line', '?')}",
            f.get("description", ""),
        )

    console = Console(stderr=True, force_terminal=True)
    with console.capture() as capture:
        console.print(table)
    return capture.get().strip()


def _select_by_input(
    findings: list[dict[str, Any]], selection: str
) -> list[dict[str, Any]]:
    sel = selection.strip().lower()
    if sel in ("all", "a"):
        return list(findings)
    if sel in ("high", "critical", "high+", "critical+"):
        return [f for f in findings if f.get("severity") in ("CRITICAL", "HIGH")]
    if sel == "medium+":
        return [
            f for f in findings if f.get("severity") in ("CRITICAL", "HIGH", "MEDIUM")
        ]
    nums: list[int] = []
    for part in re.split(r"[,\s]+", sel):
        try:
            nums.append(int(part))
        except ValueError:
            continue
    if nums:
        return [f for i, f in enumerate(findings, 1) if i in nums]
    return []


async def ask_findings_via_stdin(
    summary: str,
    prompt_fn: PromptFn | None = None,
) -> str | None:
    if not sys.stdin.isatty():
        return None
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(
        prompt,
        "Fix which findings? [all / 1,3,5 / high+ / medium+ / none]:",
        summary,
    )
    a = answer.strip().lower()
    if a in ("none", "n", "skip", "exit", "quit", "q"):
        return "none"
    if a in ("", "all", "a", "y", "yes"):
        return "all"
    return a


class ResolveFindings:
    """Pipeline node that fixes findings from upstream review nodes.

    Reads prior results from upstream nodes, extracts findings,
    optionally prompts the user for selection, then delegates
    to an inner ClaudeAgentNode to apply fixes.
    """

    def __init__(
        self,
        *,
        name: str = "resolve_findings",
        reads_from: Sequence[Any] = (),
        interactive: bool = False,
        model: str = OPUS_4_6,
        extra_skills: Sequence[str | Path] = (),
        allow: Sequence[str] | None = None,
        deny: Sequence[str] | None = None,
        on_unmatched: UnmatchedPolicy = "deny",
        max_turns: int | None = None,
        ask_findings: AskFindings = ask_findings_via_stdin,
        prompt_fn: PromptFn | None = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.interactive = interactive
        self._reads_from_keys = [_node_name(n) for n in reads_from]
        self.declared_outputs: tuple[str, ...] = (name, "last_cost_usd")
        self.on_message: Any = None
        self.prompt_fn: PromptFn | None = prompt_fn
        self._ask_findings = ask_findings
        self._ask_findings_is_default = ask_findings is ask_findings_via_stdin

        self._fixer = ClaudeAgentNode(
            name=f"{name}_inner",
            system_prompt=_SKILL,
            output=ResolveOutput,
            skills=[*extra_skills],
            allow=list(allow) if allow is not None else _ALLOW,
            deny=list(deny) if deny is not None else _DENY,
            on_unmatched=on_unmatched,
            prompt_template="{_fix_prompt}",
            model=model,
            max_turns=max_turns,
            **kwargs,
        )

    def _build_prior_results(self, state: dict[str, Any]) -> str:
        parts = ["## Prior results\n"]
        for key in self._reads_from_keys:
            upstream = state.get(key)
            if upstream is None:
                continue
            serialized = upstream.model_dump_json(indent=2)
            parts.append(f"### {key}\n```json\n{serialized}\n```\n")
        return "\n".join(parts) if len(parts) > 1 else ""

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.on_message is not None:
            self._fixer.on_message = self.on_message

        all_findings = _extract_items_from_state(self._reads_from_keys, state)

        if not all_findings:
            return {self.name: ResolveOutput(), "last_cost_usd": 0.0}

        summary = _format_findings(all_findings)

        if self.interactive:
            if self._ask_findings_is_default and self.prompt_fn is not None:
                choice = await ask_findings_via_stdin(summary, prompt_fn=self.prompt_fn)
            else:
                choice = await self._ask_findings(summary)
            if choice is None or choice == "none":
                return {
                    self.name: ResolveOutput(
                        skipped=[
                            SkippedItem(
                                file=f.get("file", "?"),
                                line=f.get("line", 0),
                                category=f.get("category", ""),
                                source=f.get("source", ""),
                                reason="user skipped",
                            )
                            for f in all_findings
                        ]
                    ),
                    "last_cost_usd": 0.0,
                }
            to_fix = _select_by_input(all_findings, choice)
        else:
            to_fix = [
                f for f in all_findings if f.get("severity") in ("CRITICAL", "HIGH")
            ]

        if not to_fix:
            return {
                self.name: ResolveOutput(
                    skipped=[
                        SkippedItem(
                            file=f.get("file", "?"),
                            line=f.get("line", 0),
                            category=f.get("category", ""),
                            source=f.get("source", ""),
                            reason="no HIGH+ severity",
                        )
                        for f in all_findings
                    ]
                ),
                "last_cost_usd": 0.0,
            }

        fix_prompt = (
            f"Fix these {len(to_fix)} issue(s):\n\n"
            f"```json\n{json.dumps(to_fix, indent=2)}\n```"
        )
        result = await self._fixer({**state, "_fix_prompt": fix_prompt})
        total_cost = result.get("last_cost_usd", 0.0)

        return {self.name: result[f"{self.name}_inner"], "last_cost_usd": total_cost}
