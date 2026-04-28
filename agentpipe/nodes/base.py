"""Node primitives.

ClaudeAgentNode wraps `claude_agent_sdk.query()` with skill injection,
per-node permissions, and a working directory pulled from state.

ShellNode runs a subprocess. Pure-Python work needs no wrapper — any
`(state) -> dict` callable is already a valid node.
"""

from __future__ import annotations

import asyncio
import enum
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)

from pydantic import BaseModel as _BaseModel

from agentpipe.budget import BudgetTracker, WarnCallback
from agentpipe.models import SONNET_4_6, resolve_model
from agentpipe.permissions import (
    PermissionRule,
    UnmatchedPolicy,
    build_can_use_tool,
)


class Verbosity(enum.Enum):
    silent = "silent"
    status = "status"
    normal = "normal"
    verbose = "verbose"


MessageCallback = Callable[[str, Any], None]


def _format_usage(usage: dict[str, Any] | None) -> str:
    if not usage:
        return ""
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    cache_create = usage.get("cache_creation_input_tokens")
    parts = []
    if in_tok is not None or out_tok is not None:
        parts.append(f"in={in_tok or 0} out={out_tok or 0}")
    if cache_read:
        parts.append(f"cache_read={cache_read}")
    if cache_create:
        parts.append(f"cache_create={cache_create}")
    return f" tokens[{' '.join(parts)}]" if parts else ""


def _make_printer(
    verbosity: Verbosity, display: Any | None = None
) -> MessageCallback | None:
    if verbosity == Verbosity.silent:
        return None
    show_usage = verbosity == Verbosity.verbose

    def _emit(node_name: str, line: str) -> None:
        if display is not None:
            display.node_output(node_name, line)
        else:
            print(f"[{node_name}] {line}", file=sys.stderr)

    def printer(node_name: str, message: Any) -> None:
        if isinstance(message, AssistantMessage):
            if show_usage:
                usage = _format_usage(getattr(message, "usage", None))
                if usage:
                    _emit(node_name, f"tokens{usage}")
            for block in message.content:
                if isinstance(block, TextBlock):
                    lines = block.text.splitlines()
                    max_lines = 5
                    for line in lines[:max_lines]:
                        _emit(node_name, line)
                    if len(lines) > max_lines:
                        _emit(node_name, f"... ({len(lines) - max_lines} more lines)")
                elif isinstance(block, ToolUseBlock):
                    args = ", ".join(f"{k}={str(v)!r}" for k, v in block.input.items())
                    _emit(node_name, f"→ {block.name}({args})")
                elif isinstance(block, ThinkingBlock):
                    _emit(node_name, "(thinking…)")
        elif isinstance(message, ResultMessage):
            if show_usage:
                cost = getattr(message, "total_cost_usd", None)
                cost_str = f" cost=${cost:.4f}" if cost is not None else ""
                usage_str = _format_usage(getattr(message, "usage", None))
                _emit(node_name, f"✓ done{cost_str}{usage_str}")
            else:
                _emit(node_name, "✓ done")

    return printer


def _split_allow(
    allow: Sequence[str], deny: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Split a unified allow list into (sdk_allowed_tools, rule_strings).

    Bare entries ("Read") fast-path through the SDK's `allowed_tools`
    *unless* a deny rule mentions the same tool — in which case they stay
    in the rule list so deny is honored. Patterned entries ("Bash(git*)")
    always go through the rule list.
    """
    deny_tools = {PermissionRule.parse(d).tool for d in deny}
    sdk_allowed: list[str] = []
    rules: list[str] = []
    for entry in allow:
        parsed = PermissionRule.parse(entry)
        if parsed.pattern is None and parsed.tool not in deny_tools:
            sdk_allowed.append(parsed.tool)
        else:
            rules.append(entry)
    return sdk_allowed, rules


def _compose_system_prompt(base: str, skill_refs: Sequence[str | Path]) -> str:
    if not skill_refs:
        return base
    parts = [base, "", "## Operating guidelines", ""]
    for ref in skill_refs:
        text = ref.read_text(encoding="utf-8") if isinstance(ref, Path) else ref
        parts.append(text)
        parts.append("")
    return "\n".join(parts).strip()


def _build_prior_results(keys: list[str], state: dict[str, Any]) -> str:
    if not keys:
        return ""
    parts = ["## Prior results\n"]
    for key in keys:
        output = state.get(key, "")
        if output:
            parts.append(f"### {key}\n{output}\n")
    return "\n".join(parts) if len(parts) > 1 else ""


def _node_name(node: Any) -> str:
    if isinstance(node, str):
        return node
    if hasattr(node, "name"):
        return node.name
    if hasattr(node, "__name__"):
        return node.__name__
    return type(node).__name__


class ClaudeAgentNode:
    """A pipeline node that runs a Claude Agent SDK query.

    The node is an async callable: `await node(state) -> dict`.
    Reads ``state["working_dir"]`` as cwd and writes output to
    ``state[self.name]``.
    """

    def __init__(
        self,
        *,
        name: str,
        display_name: str | None = None,
        system_prompt: str = "",
        output: type[_BaseModel] | None = None,
        skills: Sequence[str | Path] = (),
        allow: Sequence[str] = (),
        deny: Sequence[str] = (),
        on_unmatched: UnmatchedPolicy = "deny",
        prompt_template: str = "{task_description}",
        reads_from: Sequence[Any] = (),
        model: str = SONNET_4_6,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        hard_cap: bool = True,
        warn_at_pct: float | Sequence[float] | None = 0.8,
        on_warn: WarnCallback | None = None,
        verbosity: Verbosity = Verbosity.silent,
        on_message: MessageCallback | None = None,
        extra_options: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.display_name = display_name or name
        self.system_prompt = _compose_system_prompt(system_prompt, list(skills))
        self.allow = list(allow)
        self.deny = list(deny)
        self._sdk_allowed_tools, self._allow_rules = _split_allow(self.allow, self.deny)
        self.on_unmatched = on_unmatched
        self.prompt_template = prompt_template
        self._reads_from_keys = [_node_name(n) for n in reads_from]
        self.model = model
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.hard_cap = hard_cap
        self.warn_at_pct = self._resolve_warn_pcts(warn_at_pct, hard_cap)
        self.on_warn = on_warn
        self.verbosity = verbosity
        self.on_message: MessageCallback | None = on_message or _make_printer(verbosity)
        self.extra_options = extra_options or {}
        self.declared_outputs: tuple[str, ...] = (self.name, "last_cost_usd")
        self.output_cls: type[_BaseModel] | None = output
        if output is not None:
            from agentpipe.schema import generate_output_instructions
            self.system_prompt += "\n\n" + generate_output_instructions(output)

    @staticmethod
    def _resolve_warn_pcts(
        warn_at_pct: float | Sequence[float] | None,
        hard_cap: bool,
    ) -> float | list[float] | None:
        if hard_cap:
            if isinstance(warn_at_pct, (int, float)):
                return float(warn_at_pct)
            if warn_at_pct is not None:
                return list(warn_at_pct)
            return None
        if warn_at_pct is None:
            return [1.0]
        if isinstance(warn_at_pct, (int, float)):
            pcts = [float(warn_at_pct)]
        else:
            pcts = [float(p) for p in warn_at_pct]
        if 1.0 not in pcts:
            pcts.append(1.0)
        return pcts

    def _build_options(self, cwd: str | None) -> ClaudeAgentOptions:
        kwargs: dict[str, Any] = {
            "system_prompt": self.system_prompt,
            "allowed_tools": self._sdk_allowed_tools,
            "can_use_tool": build_can_use_tool(
                allow=self._allow_rules,
                deny=self.deny,
                on_unmatched=self.on_unmatched,
            ),
        }
        if cwd is not None:
            kwargs["cwd"] = cwd
        kwargs["model"] = resolve_model(self.model)
        if self.max_turns is not None:
            kwargs["max_turns"] = self.max_turns
        if self.max_budget_usd is not None and self.hard_cap:
            kwargs["max_budget_usd"] = self.max_budget_usd
        kwargs.update(self.extra_options)
        return ClaudeAgentOptions(**kwargs)

    def _build_prior_results(self, state: dict[str, Any]) -> str:
        return _build_prior_results(self._reads_from_keys, state)

    def _render_prompt(self, state: dict[str, Any]) -> str:
        try:
            prompt = self.prompt_template.format(**state)
        except KeyError as e:
            raise KeyError(
                f"node {self.name!r} prompt_template references missing state key: {e.args[0]!r}"
            ) from e
        prior = self._build_prior_results(state)
        if prior:
            return f"{prior}\n\n{prompt}"
        return prompt

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get("working_dir")
        prompt = self._render_prompt(state)
        options = self._build_options(cwd)

        text_chunks: list[str] = []
        result_text: str | None = None
        tracker = BudgetTracker(
            max_budget_usd=self.max_budget_usd,
            warn_at_pct=self.warn_at_pct,
            on_warn=self.on_warn,
        )

        async def _prompt_stream():
            yield {"type": "user", "message": {"role": "user", "content": prompt}}

        async for message in query(prompt=_prompt_stream(), options=options):
            tracker.observe(message)
            if self.on_message is not None:
                self.on_message(self.display_name, message)
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
            elif isinstance(message, ResultMessage):
                result_text = getattr(message, "result", None)

        final = result_text if result_text else "\n".join(text_chunks).strip()
        if self.output_cls is not None:
            from agentpipe.schema import parse_output
            final = parse_output(self.output_cls, final)
        return {
            self.name: final,
            "last_cost_usd": tracker.last_cost_usd,
        }


class ShellNode:
    """A pipeline node that runs a shell command.

    Reads ``state["working_dir"]`` as cwd and writes output to
    ``state[self.name]``.
    """

    def __init__(
        self,
        *,
        name: str,
        command: str | list[str] | Callable[[dict[str, Any]], str | list[str]],
        check: bool = True,
        timeout: float | None = None,
        verbosity: Verbosity = Verbosity.silent,
    ) -> None:
        self.name = name
        self.command = command
        self.check = check
        self.timeout = timeout
        self.verbosity = verbosity
        self.on_output: Callable[[str, str], None] | None = None
        self.declared_outputs: tuple[str, ...] = (self.name,)

    def _resolve(self, state: dict[str, Any]) -> list[str]:
        cmd = self.command(state) if callable(self.command) else self.command
        if isinstance(cmd, str):
            return shlex.split(cmd)
        return list(cmd)

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        argv = self._resolve(state)
        cwd = state.get("working_dir")

        if self.verbosity == Verbosity.silent:

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
            return {self.name: result.stdout.strip()}

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def pump(stream: asyncio.StreamReader | None, sink: list[str]) -> None:
            if stream is None:
                return
            async for raw in stream:
                line = raw.decode("utf-8", errors="replace")
                sink.append(line)
                if self.on_output is not None:
                    self.on_output(self.name, line.rstrip())
                else:
                    print(f"[{self.name}] {line.rstrip()}", file=sys.stderr)

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    pump(proc.stdout, stdout_chunks),
                    pump(proc.stderr, stderr_chunks),
                    proc.wait(),
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise subprocess.TimeoutExpired(argv, self.timeout or 0)

        if self.check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode or 1,
                argv,
                output="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
            )
        return {self.name: "".join(stdout_chunks).strip()}
