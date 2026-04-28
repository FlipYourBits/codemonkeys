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

from agentpipe.display import default_prompt as _default_prompt
from agentpipe.models import OPUS_4_6
from agentpipe.nodes.base import (
    ClaudeAgentNode,
    Verbosity,
    _build_prior_results as _build_prior,
    _node_name,
)
from agentpipe.permissions import UnmatchedPolicy

AskFindings = Callable[[str], Awaitable[str | None]]
PromptFn = Callable[[str, str | None], str]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

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
- Do not fix issues that are not in the findings list.

## Output

Final reply must be a single fenced JSON block matching
this schema and nothing after it:

```json
{
  "fixed": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "category": "logic_error",
      "source": "python_code_review",
      "description": "What was fixed, one sentence."
    }
  ],
  "skipped": [
    {
      "file": "path/to/file.py",
      "line": 10,
      "category": "clarity",
      "source": "python_code_review",
      "reason": "False positive — the code is correct because..."
    }
  ]
}
```

If nothing was fixed, return empty arrays for both fields."""

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


def _extract_findings(prior_results: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    sections = re.split(r"^### (.+)$", prior_results, flags=re.MULTILINE)
    for i in range(1, len(sections), 2):
        source = sections[i].strip()
        content = sections[i + 1] if i + 1 < len(sections) else ""
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if not json_match:
            json_match = re.search(r"(\{[\s\S]*\"findings\"[\s\S]*\})", content)
        if not json_match:
            continue
        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            continue
        for f in data.get("findings", []):
            f.setdefault("source", source)
            findings.append(f)
    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "LOW"), 99))
    return findings


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
        verbosity: Verbosity = Verbosity.silent,
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
            skills=[*extra_skills],
            allow=list(allow) if allow is not None else _ALLOW,
            deny=list(deny) if deny is not None else _DENY,
            on_unmatched=on_unmatched,
            prompt_template="{_fix_prompt}",
            model=model,
            max_turns=max_turns,
            verbosity=verbosity,
            **kwargs,
        )

    def _build_prior_results(self, state: dict[str, Any]) -> str:
        return _build_prior(self._reads_from_keys, state)

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.on_message is not None:
            self._fixer.on_message = self.on_message

        prior = self._build_prior_results(state)
        all_findings = _extract_findings(prior)

        if not all_findings:
            return {self.name: '{"fixed": [], "skipped": []}', "last_cost_usd": 0.0}

        summary = _format_findings(all_findings)

        if self.interactive:
            if self._ask_findings_is_default and self.prompt_fn is not None:
                choice = await ask_findings_via_stdin(summary, prompt_fn=self.prompt_fn)
            else:
                choice = await self._ask_findings(summary)
            if choice is None or choice == "none":
                skipped_list = [
                    {"file": f.get("file", "?"), "reason": "user skipped"}
                    for f in all_findings
                ]
                return {
                    self.name: json.dumps({"fixed": [], "skipped": skipped_list}),
                    "last_cost_usd": 0.0,
                }
            to_fix = _select_by_input(all_findings, choice)
        else:
            to_fix = [
                f for f in all_findings if f.get("severity") in ("CRITICAL", "HIGH")
            ]

        if not to_fix:
            skipped_list = [
                {"file": f.get("file", "?"), "reason": "no HIGH+ severity"}
                for f in all_findings
            ]
            return {
                self.name: json.dumps({"fixed": [], "skipped": skipped_list}),
                "last_cost_usd": 0.0,
            }

        fix_prompt = (
            f"Fix these {len(to_fix)} issue(s):\n\n"
            f"```json\n{json.dumps(to_fix, indent=2)}\n```"
        )
        result = await self._fixer({**state, "_fix_prompt": fix_prompt})
        total_cost = result.get("last_cost_usd", 0.0)

        return {self.name: result[f"{self.name}_inner"], "last_cost_usd": total_cost}
