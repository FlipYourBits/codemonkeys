"""LangGraph-compatible node primitives.

ClaudeAgentNode wraps `claude_agent_sdk.query()` with skill injection,
per-node permissions, and a working directory pulled from state.

ShellNode runs a subprocess. Pure-Python work needs no wrapper — any
`(state) -> dict` callable is already a LangGraph node.
"""

from __future__ import annotations

import asyncio
import importlib.resources as resources
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from langclaude.budget import BudgetTracker, WarnCallback
from langclaude.permissions import UnmatchedPolicy, build_can_use_tool


def _load_skill(ref: str | Path) -> str:
    """Load a skill by package-relative name or filesystem path.

    Bundled skills are referenced by stem (e.g. "python-clean-code"); they
    resolve to `langclaude/skills/<stem>.md`. Anything else is treated as a
    filesystem path.
    """
    if isinstance(ref, Path):
        return ref.read_text(encoding="utf-8")

    if "/" in ref or ref.endswith(".md"):
        return Path(ref).read_text(encoding="utf-8")

    skills_pkg = resources.files("langclaude.skills")
    candidate = skills_pkg / f"{ref}.md"
    if not candidate.is_file():
        raise FileNotFoundError(f"bundled skill not found: {ref}")
    return candidate.read_text(encoding="utf-8")


def _compose_system_prompt(base: str, skill_refs: Sequence[str | Path]) -> str:
    if not skill_refs:
        return base
    parts = [base, "", "## Operating guidelines", ""]
    for ref in skill_refs:
        parts.append(_load_skill(ref))
        parts.append("")
    return "\n".join(parts).strip()


class ClaudeAgentNode:
    """A LangGraph node that runs a Claude Agent SDK query.

    The node is an async callable: `await node(state) -> dict`. State keys
    used by default:
        - working_dir: cwd for the agent
        - task_description: passed into prompt_template

    Args:
        name: node identifier (used in error messages).
        system_prompt: base system prompt; skills are appended.
        skills: list of bundled skill names (e.g. "python-clean-code") or
            paths to .md files. Their contents are appended to system_prompt.
        allowed_tools: tools pre-approved without consulting can_use_tool.
        allow / deny: rule strings ("Bash(python*)", "Read", ...) consulted
            for any tool not in allowed_tools.
        on_unmatched: "allow" | "deny" | async callable returning bool.
        prompt_template: str.format()ed against state before sending.
        output_key: state key to write the final assistant text into.
        cwd_key: state key holding the working directory.
        model: optional Claude model id.
        max_turns: optional cap on agent turns.
        max_cost_usd: hard cost cap; the SDK aborts the run when crossed.
        warn_at_pct: emit a warning when running cost reaches this fraction
            of `max_cost_usd` (e.g. 0.8 = 80%). Ignored if max_cost_usd is
            None. Pass None to disable the warning.
        on_warn: callback `(cost, cap) -> None` for the threshold warning.
            Defaults to a stderr print.
        extra_options: dict merged into ClaudeAgentOptions for escape-hatch
            access to options not exposed here.
    """

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str = "",
        skills: Sequence[str | Path] = (),
        allowed_tools: Sequence[str] = (),
        allow: Sequence[str] = (),
        deny: Sequence[str] = (),
        on_unmatched: UnmatchedPolicy = "deny",
        prompt_template: str = "{task_description}",
        output_key: str = "last_result",
        cwd_key: str = "working_dir",
        model: str | None = None,
        max_turns: int | None = None,
        max_cost_usd: float | None = None,
        warn_at_pct: float | None = 0.8,
        on_warn: WarnCallback | None = None,
        extra_options: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = _compose_system_prompt(system_prompt, list(skills))
        self.allowed_tools = list(allowed_tools)
        self.allow = list(allow)
        self.deny = list(deny)
        self.on_unmatched = on_unmatched
        self.prompt_template = prompt_template
        self.output_key = output_key
        self.cwd_key = cwd_key
        self.model = model
        self.max_turns = max_turns
        self.max_cost_usd = max_cost_usd
        self.warn_at_pct = warn_at_pct
        self.on_warn = on_warn
        self.extra_options = extra_options or {}

    def _build_options(self, cwd: str | None) -> ClaudeAgentOptions:
        kwargs: dict[str, Any] = {
            "system_prompt": self.system_prompt,
            "allowed_tools": self.allowed_tools,
            "can_use_tool": build_can_use_tool(
                allow=self.allow,
                deny=self.deny,
                on_unmatched=self.on_unmatched,
            ),
        }
        if cwd is not None:
            kwargs["cwd"] = cwd
        if self.model is not None:
            kwargs["model"] = self.model
        if self.max_turns is not None:
            kwargs["max_turns"] = self.max_turns
        if self.max_cost_usd is not None:
            kwargs["max_budget_usd"] = self.max_cost_usd
        kwargs.update(self.extra_options)
        return ClaudeAgentOptions(**kwargs)

    def _render_prompt(self, state: dict[str, Any]) -> str:
        try:
            return self.prompt_template.format(**state)
        except KeyError as e:
            raise KeyError(
                f"node {self.name!r} prompt_template references missing state key: {e.args[0]!r}"
            ) from e

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get(self.cwd_key)
        prompt = self._render_prompt(state)
        options = self._build_options(cwd)

        text_chunks: list[str] = []
        result_text: str | None = None
        tracker = BudgetTracker(
            cap_usd=self.max_cost_usd,
            warn_at_pct=self.warn_at_pct,
            on_warn=self.on_warn,
        )

        async for message in query(prompt=prompt, options=options):
            tracker.observe(message)
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
            elif isinstance(message, ResultMessage):
                result_text = getattr(message, "result", None)

        final = result_text if result_text else "\n".join(text_chunks).strip()
        return {
            self.output_key: final,
            "last_cost_usd": tracker.last_cost_usd,
        }


class ShellNode:
    """A LangGraph node that runs a shell command.

    Args:
        name: node identifier.
        command: a string (run via shell), a list[str] (argv), or a callable
            taking state and returning either form.
        cwd_key: state key holding the working directory.
        output_key: state key to write captured stdout into.
        check: raise on non-zero exit code.
        timeout: seconds before the subprocess is killed.
    """

    def __init__(
        self,
        *,
        name: str,
        command: str | list[str] | Callable[[dict[str, Any]], str | list[str]],
        cwd_key: str = "working_dir",
        output_key: str = "last_result",
        check: bool = True,
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd_key = cwd_key
        self.output_key = output_key
        self.check = check
        self.timeout = timeout

    def _resolve(self, state: dict[str, Any]) -> tuple[list[str], bool]:
        cmd = self.command(state) if callable(self.command) else self.command
        if isinstance(cmd, str):
            return shlex.split(cmd), False
        return list(cmd), False

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        argv, _ = self._resolve(state)
        cwd = state.get(self.cwd_key)

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=self.check,
                timeout=self.timeout,
            )

        result = await asyncio.to_thread(run)
        return {self.output_key: result.stdout.strip()}
