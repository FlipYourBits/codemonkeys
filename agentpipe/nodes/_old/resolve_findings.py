"""Resolve-findings node: fixes issues from upstream review nodes.

Non-interactive (default): auto-fixes all HIGH+ severity issues.
Interactive: presents a formatted summary and lets the user pick
which findings to fix. Claude only runs for the actual fix step.
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
from agentpipe.nodes.base import ClaudeAgentNode, Verbosity
from agentpipe.permissions import UnmatchedPolicy

AskFindings = Callable[[str], Awaitable[str | None]]
PromptFn = Callable[[str, str | None], str]

_SYSTEM = (
    "You are a senior engineer fixing code issues. "
    "You will receive specific findings to fix. Make the smallest correct "
    "change per issue, verify by re-reading the file. "
    "Run tests after fixing to ensure no regressions. Do not push. "
    "Output a brief summary of what you fixed as your final message."
)

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
    "Bash(python -m pytest*)",
    "Bash(python -m unittest*)",
]

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _extract_findings(prior_results: str) -> list[dict[str, Any]]:
    """Parse JSON findings from _prior_results markdown sections."""
    findings: list[dict[str, Any]] = []
    sections = re.split(r"^### (.+)$", prior_results, flags=re.MULTILINE)
    # sections = ['', 'node_name', 'content', 'node_name', 'content', ...]
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


def _format_findings(findings: list[dict[str, Any]]) -> str:
    """Format findings as a numbered, severity-grouped summary."""
    if not findings:
        return "No findings from upstream nodes."
    lines: list[str] = []
    current_severity = ""
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "?")
        if sev != current_severity:
            current_severity = sev
            lines.append(f"\n  [{sev}]")
        src = f.get("source", "?")
        file = f.get("file", "?")
        line_num = f.get("line", "?")
        cat = f.get("category", "")
        desc = f.get("description", "")
        lines.append(f"  {i:>3}. [{src}] {file}:{line_num} ({cat})")
        lines.append(f"       {desc}")
    return "\n".join(lines)


def _select_by_input(
    findings: list[dict[str, Any]], selection: str
) -> list[dict[str, Any]]:
    """Filter findings by user selection string."""
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
        "[findings] Fix which? (all / numbers / severity / none):",
        summary,
    )
    a = answer.strip().lower()
    if a in ("none", "n", "skip", "exit", "quit", "q"):
        return "none"
    if a in ("", "all", "a", "y", "yes"):
        return "all"
    return a


def _build_prior_results(state: dict[str, Any], reads_from_keys: list[str]) -> str:
    parts = ["## Prior results\n"]
    for key in reads_from_keys:
        output = state.get(key, "")
        if output:
            parts.append(f"### {key}\n{output}\n")
    return "\n".join(parts) if len(parts) > 1 else ""


def resolve_findings_node(
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
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    from agentpipe.nodes.base import _node_name

    reads_from_keys = [_node_name(n) for n in reads_from]

    if prompt_fn is not None and ask_findings is ask_findings_via_stdin:
        from functools import partial

        ask_findings = partial(ask_findings_via_stdin, prompt_fn=prompt_fn)

    inner_name = f"{name}_inner"
    fixer = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM,
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

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        on_message = getattr(run, "on_message", None)
        if on_message is not None:
            fixer.on_message = on_message

        prior = _build_prior_results(state, reads_from_keys)
        all_findings = _extract_findings(prior)

        if not all_findings:
            return {name: '{"fixed": [], "skipped": []}', "last_cost_usd": 0.0}

        summary = _format_findings(all_findings)
        total_cost = 0.0

        if interactive:
            choice = await ask_findings(summary)
            if choice is None or choice == "none":
                return {
                    name: json.dumps({"fixed": [], "skipped": len(all_findings)}),
                    "last_cost_usd": 0.0,
                }
            to_fix = _select_by_input(all_findings, choice)
        else:
            to_fix = [
                f for f in all_findings if f.get("severity") in ("CRITICAL", "HIGH")
            ]

        if not to_fix:
            return {
                name: json.dumps({"fixed": [], "skipped": len(all_findings)}),
                "last_cost_usd": 0.0,
            }

        fix_prompt = (
            f"Fix these {len(to_fix)} issue(s):\n\n"
            f"```json\n{json.dumps(to_fix, indent=2)}\n```"
        )
        result = await fixer({**state, "_fix_prompt": fix_prompt})
        total_cost += result.get("last_cost_usd", 0.0)

        return {name: result[inner_name], "last_cost_usd": total_cost}

    run.__name__ = name
    run.on_message = None  # type: ignore[attr-defined]
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
