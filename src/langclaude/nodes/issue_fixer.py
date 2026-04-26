"""Issue-fixer node: applies fixes for findings produced by review nodes.

Pulls structured findings out of one or more state keys (default
`security_findings`), filters or prompts the user per finding, then runs
Claude in Edit/Write mode to fix each approved one. The node itself is a
plain `(state) -> dict` coroutine — LangGraph accepts that directly.

Modes
-----
- "all"          fix every parsed finding.
- "auto"         fix where severity ≥ severity_threshold and
                 confidence ≥ confidence_threshold. Good for CI.
- "interactive"  prompt y/n/a/q per finding on stdin. Falls back to "auto"
                 when stdin isn't a TTY (CI, pipes).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.findings import (
    dedupe_findings,
    parse_findings,
    passes_threshold,
)
from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["interactive", "auto", "all"]
AskFinding = Callable[[dict[str, Any]], Awaitable[str]]

_SYSTEM_PROMPT = (
    "You are a senior engineer applying a targeted fix for a known issue. "
    "Read the affected file, make the smallest correct change that resolves "
    "the issue per its recommendation, and verify by re-reading. Do not "
    "refactor unrelated code. Do not commit or push. Report what you changed."
)

_DEFAULT_ALLOW: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
)

_DEFAULT_DENY: tuple[str, ...] = (
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(rm -rf*)",
    "Bash(rm*)",
)


async def ask_finding_via_stdin(finding: dict[str, Any]) -> str:
    """Prompt user about a single finding. Returns 'y', 'n', 'a', or 'q'.

    'y' = fix this one, 'n' = skip, 'a' = fix all remaining, 'q' = stop.
    Returns 'n' when stdin isn't a TTY.
    """
    if not sys.stdin.isatty():
        return "n"
    summary = (
        f"\n[langclaude] {finding.get('severity', '?')} "
        f"{finding.get('category', '?')} at "
        f"{finding.get('file', '?')}:{finding.get('line', '?')}\n"
        f"  {finding.get('description', '')}\n"
        f"  recommendation: {finding.get('recommendation', '')}\n"
        f"Fix? [y]es / [n]o / [a]ll remaining / [q]uit: "
    )
    answer = await asyncio.to_thread(input, summary)
    a = answer.strip().lower()[:1]
    return a if a in ("y", "n", "a", "q") else "n"


def _build_fix_prompt(finding: dict[str, Any]) -> str:
    parts = [
        f"Fix this issue: {finding.get('category', 'issue')} at "
        f"{finding.get('file', '?')}:{finding.get('line', '?')}.",
        "",
        f"Severity: {finding.get('severity', 'unknown')}",
        f"Source: {finding.get('source', 'unknown')}",
        f"Description: {finding.get('description', '')}",
        f"Recommendation: {finding.get('recommendation', '')}",
    ]
    if finding.get("exploit_scenario"):
        parts.append(f"Exploit scenario: {finding['exploit_scenario']}")
    parts.extend(
        [
            "",
            "Make the smallest correct change. Do not refactor unrelated "
            "code. Verify by re-reading the file after the edit.",
        ]
    )
    return "\n".join(parts)


async def _select(
    findings: list[dict[str, Any]],
    *,
    mode: Mode,
    severity_threshold: str,
    confidence_threshold: float,
    ask: AskFinding,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (approved, skipped). `mode` may auto-downgrade for non-TTY."""
    effective: Mode = mode
    if mode == "interactive" and not sys.stdin.isatty():
        effective = "auto"

    if effective == "all":
        return list(findings), []

    if effective == "auto":
        approved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for f in findings:
            if passes_threshold(
                f,
                severity_threshold=severity_threshold,
                confidence_threshold=confidence_threshold,
            ):
                approved.append(f)
            else:
                skipped.append(f)
        return approved, skipped

    approved = []
    skipped = []
    fix_all = False
    quit_loop = False
    for f in findings:
        if quit_loop:
            skipped.append(f)
            continue
        if fix_all:
            approved.append(f)
            continue
        ans = await ask(f)
        if ans == "y":
            approved.append(f)
        elif ans == "a":
            approved.append(f)
            fix_all = True
        elif ans == "q":
            skipped.append(f)
            quit_loop = True
        else:
            skipped.append(f)
    return approved, skipped


def claude_issue_fixer_node(
    *,
    name: str = "issue_fixer",
    findings_keys: Sequence[str] = ("security_findings",),
    mode: Mode = "interactive",
    severity_threshold: str = "HIGH",
    confidence_threshold: float = 0.8,
    one_at_a_time: bool = False,
    ask: AskFinding = ask_finding_via_stdin,
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] = _DEFAULT_ALLOW,
    deny: Sequence[str] = _DEFAULT_DENY,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "applied_fixes",
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a fixer node that applies review-node findings to the codebase.

    State input:
        working_dir: cwd for the inner Claude agent.
        any of `findings_keys`: text or already-parsed findings from review
            nodes. Missing keys are skipped silently.

    State output:
        `output_key` (default "applied_fixes"): list of {finding, summary}.
        "skipped_findings": list of finding dicts not fixed.
        "last_cost_usd": cumulative cost of fix runs added to whatever
            cost was already in state.

    Args:
        findings_keys: state keys to pull findings from.
        mode: "interactive" | "auto" | "all". Interactive falls back to
            auto when stdin isn't a TTY.
        severity_threshold / confidence_threshold: gates for auto mode.
        one_at_a_time: True (default) runs one Claude pass per finding —
            slower but isolated. False bundles all approved findings into
            one prompt.
        ask: async callback used in interactive mode.
        extra_skills: language/domain skill files to inject.
        allow / deny / on_unmatched / model / max_turns / **kwargs: passed
            through to the inner ClaudeAgentNode.
    """
    skills = [*extra_skills]

    fix_node = ClaudeAgentNode(
        name=f"{name}_inner",
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        allow=list(allow),
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="{__fix_prompt__}",
        output_key="last_result",
        model=model,
        max_turns=max_turns,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for key in findings_keys:
            findings.extend(parse_findings(state.get(key)))
        findings = dedupe_findings(findings)

        approved, skipped = await _select(
            findings,
            mode=mode,
            severity_threshold=severity_threshold,
            confidence_threshold=confidence_threshold,
            ask=ask,
        )

        applied: list[dict[str, Any]] = []
        total_cost = float(state.get("last_cost_usd") or 0.0)

        if one_at_a_time:
            for f in approved:
                child = {**state, "__fix_prompt__": _build_fix_prompt(f)}
                result = await fix_node(child)
                applied.append(
                    {"finding": f, "summary": result.get("last_result", "")}
                )
                total_cost += float(result.get("last_cost_usd") or 0.0)
        elif approved:
            bulk = (
                "Fix the following issues, one at a time, smallest correct "
                "change for each:\n\n"
                + "\n\n---\n\n".join(_build_fix_prompt(f) for f in approved)
            )
            result = await fix_node({**state, "__fix_prompt__": bulk})
            summary = result.get("last_result", "")
            applied = [{"finding": f, "summary": summary} for f in approved]
            total_cost += float(result.get("last_cost_usd") or 0.0)

        return {
            output_key: applied,
            "skipped_findings": skipped,
            "last_cost_usd": total_cost,
        }

    run.__name__ = name
    run.declared_outputs = (output_key, "skipped_findings", "last_cost_usd")  # type: ignore[attr-defined]
    return run


def claude_python_issue_fixer_node(
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    kwargs.setdefault("name", "python_issue_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_issue_fixer_node(
        extra_skills=["python-clean-code", *extra], **kwargs
    )


def claude_javascript_issue_fixer_node(
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    kwargs.setdefault("name", "javascript_issue_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_issue_fixer_node(
        extra_skills=["javascript-clean-code", *extra], **kwargs
    )


def claude_rust_issue_fixer_node(
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    kwargs.setdefault("name", "rust_issue_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_issue_fixer_node(
        extra_skills=["rust-clean-code", *extra], **kwargs
    )
