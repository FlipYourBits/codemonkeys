"""Reusable agent runner with Rich live display."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    ToolUseBlock,
    query,
)
from rich.console import Console
from rich.live import Live
from rich.text import Text

from codemonkeys.ui import AgentState, render_agent_table, summarize_tool


class _Display:
    _TOP_LEVEL_ID = "__top__"

    def __init__(self, label: str = "Agent") -> None:
        self.label = label
        self.agents: dict[str, AgentState] = {
            self._TOP_LEVEL_ID: AgentState(name=label, started=time.monotonic()),
        }
        self.total_tokens = 0
        self._has_subagents = False
        self._spinner_idx = 0

    def add_usage(self, usage: dict | None) -> None:
        if not usage:
            return
        turn_tokens = usage.get("total_tokens", 0) or (
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
        self.total_tokens += turn_tokens
        self.agents[self._TOP_LEVEL_ID].tokens = self.total_tokens

    def set_usage(self, usage: dict | None) -> None:
        if not usage:
            return
        self.total_tokens = usage.get("total_tokens", 0) or (
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
        self.agents[self._TOP_LEVEL_ID].tokens = self.total_tokens

    def tool_used(self, detail: str) -> None:
        self.agents[self._TOP_LEVEL_ID].last_tool = detail

    def start_agent(self, task_id: str, description: str) -> None:
        self._has_subagents = True
        self.agents[task_id] = AgentState(name=description, started=time.monotonic())

    def progress_agent(self, task_id: str, tokens: int, tool_uses: int = 0) -> None:
        if task_id in self.agents:
            self.agents[task_id].tokens = tokens
            self.total_tokens = sum(a.tokens for a in self.agents.values())

    def done_agent(self, task_id: str, tokens: int | None = None) -> None:
        if task_id in self.agents:
            self.agents[task_id].status = "complete"
            self.agents[task_id].end_time = time.monotonic()
            if tokens is not None:
                self.agents[task_id].tokens = tokens
                self.total_tokens = sum(a.tokens for a in self.agents.values())

    def finish_top_level(self) -> None:
        top = self.agents[self._TOP_LEVEL_ID]
        top.status = "complete"
        top.end_time = time.monotonic()

    def agent_activity(self, task_id: str, detail: str) -> None:
        if task_id in self.agents and self.agents[task_id].status == "running":
            self.agents[task_id].last_tool = detail

    def render(self) -> Text:
        self._spinner_idx += 1
        cols = os.get_terminal_size().columns
        table = render_agent_table(
            self.agents,
            time.monotonic(),
            self._spinner_idx,
            cols,
        )
        return Text(table)


def _tool_detail(block: ToolUseBlock) -> str:
    return summarize_tool(block.name, block.input or {})


class AgentRunner:
    """Runs agents or workflows with a Rich live display.

    For single agents, shows current tool activity and call count.
    For workflows with subagents, shows a table with per-agent status.

    Usage::

        runner = AgentRunner()

        # Run a single agent directly
        result = await runner.run_agent(make_python_quality_reviewer(), "Review the diff")

        # Run with full ClaudeAgentOptions (workflows, custom config)
        result = await runner.run(options, "Dispatch all agents")

        # Access the raw ResultMessage after a run
        msg = runner.last_result
    """

    def __init__(self, cwd: str = ".", label: str = "Agent") -> None:
        self.cwd = cwd
        self.label = label
        self.last_result: ResultMessage | None = None
        self._console = Console(stderr=True)

    async def run(self, options: ClaudeAgentOptions, prompt: str) -> str:
        from codemonkeys.sandbox import restrict

        restrict(self.cwd)

        display = _Display(label=self.label)
        last_active_tid: str | None = None
        result_text = ""

        async def _prompt():
            yield {
                "type": "user",
                "message": {"role": "user", "content": prompt},
            }

        async def _refresh(live: Live) -> None:
            while True:
                await asyncio.sleep(0.1)
                live.update(display.render())

        with Live(
            display.render(), console=self._console, refresh_per_second=10
        ) as live:
            refresh_task = asyncio.create_task(_refresh(live))
            try:
                async for message in query(prompt=_prompt(), options=options):
                    last_active_tid = self._handle_message(
                        message, display, last_active_tid
                    )
                    if isinstance(message, ResultMessage):
                        result_text = getattr(message, "result", "") or ""
                        display.set_usage(message.usage)
                        display.finish_top_level()
                        self.last_result = message
            finally:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
                live.update(display.render())

        return result_text

    def _handle_message(
        self,
        message: Any,
        display: _Display,
        last_active_tid: str | None,
    ) -> str | None:
        if isinstance(message, AssistantMessage):
            if not display._has_subagents:
                display.add_usage(message.usage)
            for block in message.content:
                if isinstance(block, ToolUseBlock) and block.name != "Agent":
                    detail = _tool_detail(block)
                    if display._has_subagents and last_active_tid:
                        display.agent_activity(last_active_tid, detail)
                    else:
                        display.tool_used(detail)
            return last_active_tid

        if isinstance(message, TaskStartedMessage):
            display.start_agent(message.task_id, message.description)
            return message.task_id

        if isinstance(message, TaskProgressMessage):
            usage = message.usage
            if usage is None:
                tokens = 0
                tools = 0
            else:
                tokens = (
                    usage["total_tokens"]
                    if isinstance(usage, dict)
                    else getattr(usage, "total_tokens", 0)
                )
                tools = (
                    usage.get("tool_uses", 0)
                    if isinstance(usage, dict)
                    else getattr(usage, "tool_uses", 0)
                )
            display.progress_agent(
                message.task_id,
                tokens=tokens,
                tool_uses=tools,
            )
            if message.last_tool_name:
                if display._has_subagents:
                    display.agent_activity(message.task_id, message.last_tool_name)
                else:
                    display.tool_used(message.last_tool_name)
            return message.task_id

        if isinstance(message, TaskNotificationMessage):
            final_usage = message.usage
            final_tokens = None
            if final_usage:
                final_tokens = (
                    final_usage["total_tokens"]
                    if isinstance(final_usage, dict)
                    else getattr(final_usage, "total_tokens", 0)
                )
            display.done_agent(message.task_id, tokens=final_tokens)
            return last_active_tid

        return last_active_tid

    async def run_agent(
        self,
        agent: AgentDefinition,
        prompt: str,
        *,
        output_format: dict[str, Any] | None = None,
    ) -> str:
        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=self.cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=agent.tools or [],
            disallowed_tools=agent.disallowedTools or [],
            output_format=output_format,
        )
        return await self.run(options, prompt)


def run_cli(
    agent: AgentDefinition,
    prompt: str,
    output_format: dict[str, Any] | None = None,
) -> None:
    """Run an agent from the command line and print the result."""

    async def _main() -> None:
        runner = AgentRunner()
        result = await runner.run_agent(agent, prompt, output_format=output_format)
        print(result)

    asyncio.run(_main())
