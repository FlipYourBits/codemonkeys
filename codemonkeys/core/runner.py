"""Reusable agent runner with Rich live display and filesystem sandboxing."""

from __future__ import annotations

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
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text


def _tool_detail(block: ToolUseBlock) -> str:
    name = block.name
    tool_input = block.input or {}
    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "?")
        return f"{name}({path})"
    if name == "Grep":
        return f"Grep('{tool_input.get('pattern', '?')}')"
    if name == "Glob":
        return f"Glob({tool_input.get('pattern', tool_input.get('path', '?'))})"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:80]})" if cmd else "Bash"
    return name


class _Display:
    def __init__(self) -> None:
        self.agents: dict[str, dict[str, Any]] = {}
        self.status = "running"
        self.activity = ""
        self.tool_calls = 0
        self.total_tokens = 0
        self.cost: float | None = None
        self._has_subagents = False

    def add_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        turn_tokens = usage.get("total_tokens", 0) or (
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
        self.total_tokens += turn_tokens

    def set_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        self.total_tokens = usage.get("total_tokens", 0) or (
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )

    def tool_used(self, detail: str) -> None:
        self.activity = detail
        self.tool_calls += 1

    def start_agent(self, task_id: str, description: str) -> None:
        self._has_subagents = True
        self.agents[task_id] = {
            "name": description,
            "status": "running",
            "activity": "starting...",
            "calls": 0,
            "tokens": 0,
        }
        self._update_status()

    def progress_agent(self, task_id: str, tokens: int, tool_uses: int = 0) -> None:
        if task_id in self.agents:
            self.agents[task_id]["tokens"] = tokens
            self.agents[task_id]["calls"] = tool_uses
            self.total_tokens = sum(a["tokens"] for a in self.agents.values())

    def done_agent(self, task_id: str, tokens: int | None = None) -> None:
        if task_id in self.agents:
            self.agents[task_id]["status"] = "done"
            self.agents[task_id]["activity"] = "complete"
            if tokens is not None:
                self.agents[task_id]["tokens"] = tokens
                self.total_tokens = sum(a["tokens"] for a in self.agents.values())
        self._update_status()

    def agent_activity(self, task_id: str, detail: str) -> None:
        if task_id in self.agents and self.agents[task_id]["status"] == "running":
            self.agents[task_id]["activity"] = detail

    def _update_status(self) -> None:
        running = sum(1 for a in self.agents.values() if a["status"] == "running")
        if running == 0:
            self.status = "summarizing..."
        else:
            self.status = f"waiting for {running} agent{'s' if running != 1 else ''}..."

    def render(self) -> Group | Text:
        cost_str = f"  ${self.cost:.4f}" if self.cost else ""

        if self._has_subagents:
            header = Text(
                f"Coordinator: {self.status}  [{self.total_tokens:,} tokens{cost_str}]",
                style="bold",
            )
            table = Table(show_header=True, expand=True, padding=(0, 1))
            table.add_column("Agent", style="bold cyan", no_wrap=True)
            table.add_column("Status", width=8)
            table.add_column("Activity", style="dim")
            table.add_column("Tokens", justify="right", width=10)
            table.add_column("Tools", justify="right", width=5)

            for info in self.agents.values():
                status = (
                    Text("running", style="yellow")
                    if info["status"] == "running"
                    else Text("done", style="green")
                )
                table.add_row(
                    info["name"],
                    status,
                    info["activity"][:50],
                    f"{info['tokens']:,}",
                    str(info["calls"]),
                )
            return Group(header, table)

        parts = [self.status]
        if self.activity:
            parts.append(self.activity)
        tokens_str = f"  {self.total_tokens:,} tokens" if self.total_tokens else ""
        parts.append(
            f"[{self.tool_calls} tool{'s' if self.tool_calls != 1 else ''}"
            f"{tokens_str}{cost_str}]"
        )
        return Text("  ".join(parts), style="bold")


class AgentRunner:
    """Runs agents with a Rich live display and filesystem sandboxing.

    Usage::

        runner = AgentRunner(cwd="/path/to/project")
        result = await runner.run_agent(make_python_file_reviewer(["src/main.py"]), "Review: src/main.py")
    """

    def __init__(self, cwd: str = ".") -> None:
        self.cwd = cwd
        self.last_result: ResultMessage | None = None
        self._console = Console(stderr=True)

    async def run(self, options: ClaudeAgentOptions, prompt: str) -> str:
        from codemonkeys.core.sandbox import restrict

        restrict(self.cwd)

        display = _Display()
        last_active_tid: str | None = None
        result_text = ""

        async def _prompt():
            yield {
                "type": "user",
                "message": {"role": "user", "content": prompt},
            }

        with Live(
            display.render(), console=self._console, refresh_per_second=4
        ) as live:
            async for message in query(prompt=_prompt(), options=options):
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
                    live.update(display.render())

                elif isinstance(message, TaskStartedMessage):
                    display.start_agent(message.task_id, message.description)
                    last_active_tid = message.task_id
                    live.update(display.render())

                elif isinstance(message, TaskProgressMessage):
                    last_active_tid = message.task_id
                    u = message.usage
                    tokens = (
                        u["total_tokens"]
                        if isinstance(u, dict)
                        else getattr(u, "total_tokens", 0)
                    )
                    tools = (
                        u.get("tool_uses", 0)
                        if isinstance(u, dict)
                        else getattr(u, "tool_uses", 0)
                    )
                    display.progress_agent(
                        message.task_id,
                        tokens=tokens,
                        tool_uses=tools,
                    )
                    live.update(display.render())

                elif isinstance(message, TaskNotificationMessage):
                    u = message.usage
                    final_tokens = None
                    if u:
                        final_tokens = (
                            u["total_tokens"]
                            if isinstance(u, dict)
                            else getattr(u, "total_tokens", 0)
                        )
                    display.done_agent(message.task_id, tokens=final_tokens)
                    live.update(display.render())

                elif isinstance(message, ResultMessage):
                    result_text = getattr(message, "result", "") or ""
                    display.set_usage(message.usage)
                    display.cost = getattr(message, "total_cost_usd", None)
                    display.status = "done"
                    self.last_result = message
                    live.update(display.render())

        return result_text

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
            allowed_tools=agent.tools,
            disallowed_tools=agent.disallowedTools or [],
            output_format=output_format,
        )
        return await self.run(options, prompt)
