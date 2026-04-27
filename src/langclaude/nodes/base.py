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
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from langclaude.budget import BudgetTracker, WarnCallback
from langclaude.permissions import (
    PermissionRule,
    UnmatchedPolicy,
    build_can_use_tool,
)


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

    skills_pkg = resources.files(anchor="langclaude.skills")
    candidate = skills_pkg / f"{ref}.md"
    if not candidate.is_file():
        raise FileNotFoundError(f"bundled skill not found: {ref}")
    return candidate.read_text(encoding="utf-8")


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


def _default_printer(node_name: str, message: Any) -> None:
    """Print full progress output per agent message to stderr."""
    prefix = f"[{node_name}]"
    if isinstance(message, AssistantMessage):
        usage = _format_usage(getattr(message, "usage", None))
        if usage:
            print(f"{prefix}{usage}", file=sys.stderr)
        for block in message.content:
            if isinstance(block, TextBlock):
                for line in block.text.splitlines():
                    print(f"{prefix} {line}", file=sys.stderr)
            elif isinstance(block, ToolUseBlock):
                args = ", ".join(f"{k}={str(v)!r}" for k, v in block.input.items())
                print(f"{prefix} → {block.name}({args})", file=sys.stderr)
            elif isinstance(block, ThinkingBlock):
                print(f"{prefix} (thinking…)", file=sys.stderr)
            elif isinstance(block, ToolResultBlock):
                content = getattr(block, "content", "")
                if isinstance(content, list):
                    content = " ".join(
                        getattr(c, "text", "") for c in content if hasattr(c, "text")
                    )
                for line in str(content).splitlines():
                    print(f"{prefix} ← {line}", file=sys.stderr)
    elif isinstance(message, ResultMessage):
        cost = getattr(message, "total_cost_usd", None)
        cost_str = f" cost=${cost:.4f}" if cost is not None else ""
        usage_str = _format_usage(getattr(message, "usage", None))
        print(f"{prefix} ✓ done{cost_str}{usage_str}", file=sys.stderr)


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
        allow / deny: rule strings matching Claude Code's settings.json
            syntax: bare names ("Read") or patterns ("Bash(python*)").
            Bare names with no matching deny rule are routed to the SDK's
            fast-path auto-allow; everything else runs through can_use_tool.
            Deny always wins.
        on_unmatched: "allow" | "deny" | async callable returning bool.
        prompt_template: str.format()ed against state before sending.
        output_key: state key to write the final assistant text into.
        cwd_key: state key holding the working directory.
        model: optional Claude model id.
        max_turns: optional cap on agent turns.
        max_budget_usd: cost cap. With hard_cap=True (default) the SDK aborts
            the run when crossed; with hard_cap=False it is only used to
            compute warning thresholds.
        hard_cap: if True (default) pass `max_budget_usd` to the SDK so the
            run is killed when crossed. If False, the run is not killed —
            but a warning still fires when 100% is reached (1.0 is added to
            warn_at_pct automatically when missing).
        warn_at_pct: a single fraction in (0, 1] or a list of fractions at
            which to emit a warning (e.g. [0.8, 0.9, 0.95]). Ignored if
            max_budget_usd is None. Pass None to disable warnings.
        on_warn: callback `(cost, cap) -> None` for threshold warnings.
            Defaults to a stderr print.
        verbose: if True, print one short stderr line per streamed message
            (text deltas, tool calls, results). Equivalent to setting
            `on_message` to a default printer.
        on_message: callback `(node_name, message) -> None` invoked for
            every message yielded by the SDK. Use this to plug into a
            logger or TUI. Overrides `verbose` when both are set.
        extra_options: dict merged into ClaudeAgentOptions for escape-hatch
            access to options not exposed here.
    """

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str = "",
        skills: Sequence[str | Path] = (),
        allow: Sequence[str] = (),
        deny: Sequence[str] = (),
        on_unmatched: UnmatchedPolicy = "deny",
        prompt_template: str = "{task_description}",
        output_key: str = "last_result",
        cwd_key: str = "working_dir",
        model: str | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        hard_cap: bool = True,
        warn_at_pct: float | Sequence[float] | None = 0.8,
        on_warn: WarnCallback | None = None,
        verbose: bool = False,
        on_message: MessageCallback | None = None,
        extra_options: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = _compose_system_prompt(system_prompt, list(skills))
        self.allow = list(allow)
        self.deny = list(deny)
        self._sdk_allowed_tools, self._allow_rules = _split_allow(self.allow, self.deny)
        self.on_unmatched = on_unmatched
        self.prompt_template = prompt_template
        self.output_key = output_key
        self.cwd_key = cwd_key
        self.model = model
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.hard_cap = hard_cap
        self.warn_at_pct = self._resolve_warn_pcts(warn_at_pct, hard_cap)
        self.on_warn = on_warn
        self.on_message: MessageCallback | None = on_message or (
            _default_printer if verbose else None
        )
        self.extra_options = extra_options or {}
        self.declared_outputs: tuple[str, ...] = (self.output_key, "last_cost_usd")

    @staticmethod
    def _resolve_warn_pcts(
        warn_at_pct: float | Sequence[float] | None,
        hard_cap: bool,
    ) -> float | list[float] | None:
        if hard_cap:
            return warn_at_pct
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
        if self.model is not None:
            kwargs["model"] = self.model
        if self.max_turns is not None:
            kwargs["max_turns"] = self.max_turns
        if self.max_budget_usd is not None and self.hard_cap:
            kwargs["max_budget_usd"] = self.max_budget_usd
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
            max_budget_usd=self.max_budget_usd,
            warn_at_pct=self.warn_at_pct,
            on_warn=self.on_warn,
        )

        async def _prompt_stream():
            # The SDK requires AsyncIterable when can_use_tool is set,
            # which we always do. Wrap the rendered prompt accordingly.
            yield {"type": "user", "message": {"role": "user", "content": prompt}}

        async for message in query(prompt=_prompt_stream(), options=options):
            tracker.observe(message)
            if self.on_message is not None:
                self.on_message(self.name, message)
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
        verbose: if True, also echo each stdout line to stderr as it
            arrives, prefixed with the node name. Captured stdout is
            still written to `output_key` either way.
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
        verbose: bool = False,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd_key = cwd_key
        self.output_key = output_key
        self.check = check
        self.timeout = timeout
        self.verbose = verbose
        self.declared_outputs: tuple[str, ...] = (self.output_key,)

    def _resolve(self, state: dict[str, Any]) -> tuple[list[str], bool]:
        cmd = self.command(state) if callable(self.command) else self.command
        if isinstance(cmd, str):
            return shlex.split(cmd), False
        return list(cmd), False

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        argv, _ = self._resolve(state)
        cwd = state.get(self.cwd_key)

        if not self.verbose:

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

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        prefix = f"[{self.name}]"
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def pump(stream: asyncio.StreamReader | None, sink: list[str]) -> None:
            if stream is None:
                return
            async for raw in stream:
                line = raw.decode("utf-8", errors="replace")
                sink.append(line)
                print(f"{prefix} {line.rstrip()}", file=sys.stderr)

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
        return {self.output_key: "".join(stdout_chunks).strip()}
