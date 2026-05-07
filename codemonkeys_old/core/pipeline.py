"""Pipeline — composable agent orchestration with Rich display.

A pipeline is an async function that uses a PipelineContext to run agents.
The context handles display, logging, and parallel execution.

    async def my_pipeline(ctx: PipelineContext, files: list[str]):
        with ctx.phase("review"):
            results = await ctx.run_parallel([...])

        choice = ctx.prompt("What to fix?", options=["all", "skip"])

        with ctx.phase("fix"):
            await ctx.run_parallel([...])
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from claude_agent_sdk import AgentDefinition
from rich.console import Console
from rich.panel import Panel

from codemonkeys.core.run_result import RunResult
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.display import WorkflowDisplay
from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    PhaseCompletedPayload,
    PhaseStartedPayload,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow

T = TypeVar("T")


def chunked(items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class PipelineContext:
    """Everything a pipeline needs to run agents and display progress."""

    def __init__(self, name: str, phases: list[str], cwd: str = ".") -> None:
        self.name = name
        self.cwd = cwd

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        self.log_dir = Path(cwd) / ".codemonkeys" / "logs" / ts
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._emitter = EventEmitter()
        self._console = Console()
        self._runner = AgentRunner(cwd=cwd, emitter=self._emitter, log_dir=self.log_dir)

        workflow = Workflow(
            name=name,
            phases=[
                Phase(name=p, phase_type=PhaseType.AGENT, execute=None)  # type: ignore[arg-type]
                for p in phases
            ],
        )
        self._display = WorkflowDisplay(workflow, self._emitter)

    def start(self) -> None:
        self._console.print(
            Panel(
                f"[dim]Logs:[/dim] {self.log_dir}",
                title=f"[bold]{self.name}[/bold]",
                border_style="bright_blue",
            )
        )
        self._display.start()

    def stop(self) -> None:
        self._display.stop()

    @contextlib.contextmanager
    def phase(self, name: str):
        self._emitter.emit(
            EventType.PHASE_STARTED,
            PhaseStartedPayload(phase=name, workflow=self.name),
        )
        try:
            yield
        finally:
            self._emitter.emit(
                EventType.PHASE_COMPLETED,
                PhaseCompletedPayload(phase=name, workflow=self.name),
            )

    async def run(
        self,
        agent: AgentDefinition,
        prompt: str,
        *,
        output_format: dict[str, Any] | None = None,
        log_name: str = "agent",
        files: str = "",
    ) -> RunResult:
        return await self._runner.run_agent(
            agent, prompt, output_format=output_format, log_name=log_name, files=files
        )

    async def run_parallel(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[RunResult]:
        coros = []
        for task in tasks:
            agent = task.pop("agent")
            prompt = task.pop("prompt")
            coros.append(self._runner.run_agent(agent, prompt, **task))
        return list(await asyncio.gather(*coros))

    def prompt(self, message: str, *, options: list[str] | None = None) -> str:
        self._display.pause()
        lines = f"[bold]{message}[/bold]"
        if options:
            lines += "\n" + "\n".join(f'  [dim]"{o}"[/dim]' for o in options)
        self._console.print(Panel(lines, border_style="yellow", padding=(1, 2)))
        choice = self._console.input("  [bold]>[/bold] ").strip()
        self._display.resume()
        return choice
