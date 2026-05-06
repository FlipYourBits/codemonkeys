"""Unified CLI display for workflow execution.

Subscribes to workflow events and renders a single Rich Live display with:
- Phase checklist (pending/running/done)
- Per-agent cards within the active phase
- Mechanical tool results
- Fix progress
- Cumulative token total
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    TriageReadyPayload,
    WorkflowErrorPayload,
)
from codemonkeys.workflows.phases import Workflow

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class WorkflowDisplay:
    def __init__(
        self,
        workflow: Workflow,
        emitter: EventEmitter,
        console: Console | None = None,
    ) -> None:
        self._console = console or Console(stderr=True)
        self._phases = [p.name for p in workflow.phases]
        self._phase_status: dict[str, str] = {p: "pending" for p in self._phases}
        self._agents: dict[str, dict[str, Any]] = {}
        self._mechanical_tools: list[dict[str, Any]] = []
        self._current_tool: str | None = None
        self._fix_files: list[dict[str, str]] = []
        self._triage_info: str = ""
        self._error: str | None = None
        self._cumulative_tokens: int = 0
        self._live: Live | None = None
        self._tick: int = 0

        emitter.on(EventType.PHASE_STARTED, self._on_phase_started)
        emitter.on(EventType.PHASE_COMPLETED, self._on_phase_completed)
        emitter.on(EventType.AGENT_STARTED, self._on_agent_started)
        emitter.on(EventType.AGENT_PROGRESS, self._on_agent_progress)
        emitter.on(EventType.AGENT_COMPLETED, self._on_agent_completed)
        emitter.on(EventType.MECHANICAL_TOOL_STARTED, self._on_tool_started)
        emitter.on(EventType.MECHANICAL_TOOL_COMPLETED, self._on_tool_completed)
        emitter.on(EventType.TRIAGE_READY, self._on_triage_ready)
        emitter.on(EventType.FIX_PROGRESS, self._on_fix_progress)
        emitter.on(EventType.WORKFLOW_COMPLETED, self._on_completed)
        emitter.on(EventType.WORKFLOW_ERROR, self._on_error)

    def start(self) -> None:
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=4,
            vertical_overflow="visible",
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def pause(self) -> None:
        if self._live:
            self._live.stop()

    def resume(self) -> None:
        if self._live:
            self._live.start()
        else:
            self.start()

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _spinner(self) -> str:
        self._tick += 1
        return _SPINNER_FRAMES[self._tick % len(_SPINNER_FRAMES)]

    def _render(self) -> Group:
        parts: list[Text | Table] = []

        if self._cumulative_tokens > 0:
            header = Text(f"  [{self._cumulative_tokens:,} tokens total]", style="dim")
            parts.append(header)

        for name in self._phases:
            status = self._phase_status[name]
            line = Text()
            if status == "done":
                line.append("  ✓ ", style="green")
                line.append(name.replace("_", " "), style="green")
            elif status == "running":
                line.append(f"  {self._spinner()} ", style="yellow")
                line.append(name.replace("_", " "), style="bold yellow")
            else:
                line.append("  ○ ", style="dim")
                line.append(name.replace("_", " "), style="dim")
            parts.append(line)

            if (
                name == "mechanical_audit"
                and status == "running"
                and self._current_tool
            ):
                tool_line = Text()
                tool_line.append(
                    f"      {self._spinner()} {self._current_tool}...", style="dim"
                )
                parts.append(tool_line)

            if name == "mechanical_audit" and self._mechanical_tools:
                for tool_info in self._mechanical_tools:
                    tool_line = Text()
                    tool_line.append(f"      ✓ {tool_info['tool']}", style="dim green")
                    tool_line.append(
                        f"  {tool_info['findings']} finding"
                        f"{'s' if tool_info['findings'] != 1 else ''}",
                        style="dim",
                    )
                    tool_line.append(f"  {tool_info['duration_ms']}ms", style="dim")
                    parts.append(tool_line)

            if status == "running" and self._agents:
                table = Table(show_header=True, expand=True, padding=(0, 1), box=None)
                table.add_column("Agent", style="bold cyan", no_wrap=True)
                table.add_column("Model", width=8, style="dim")
                table.add_column("Status", width=8)
                table.add_column("Activity", style="dim")
                table.add_column("Tokens", justify="right", width=10)
                table.add_column("Tools", justify="right", width=5)

                for info in self._agents.values():
                    status_text = (
                        Text("running", style="yellow")
                        if info["status"] == "running"
                        else Text("done", style="green")
                    )
                    table.add_row(
                        info["name"],
                        info.get("model", ""),
                        status_text,
                        info.get("current_tool", ""),
                        f"{info.get('tokens', 0):,}",
                        str(info.get("tool_calls", 0)),
                    )
                parts.append(table)

            if name == "triage" and self._triage_info:
                info_line = Text()
                info_line.append(f"      {self._triage_info}", style="dim")
                parts.append(info_line)

            if name == "fix" and self._fix_files:
                for fix_info in self._fix_files:
                    fix_line = Text()
                    if fix_info["status"] == "started":
                        fix_line.append(
                            f"      {self._spinner()} {fix_info['file']}",
                            style="yellow",
                        )
                    elif fix_info["status"] == "completed":
                        fix_line.append(f"      ✓ {fix_info['file']}", style="green")
                    else:
                        fix_line.append(f"      ✗ {fix_info['file']}", style="red")
                    parts.append(fix_line)

        if self._error:
            err_line = Text()
            err_line.append(f"\n  Error: {self._error}", style="bold red")
            parts.append(err_line)

        return Group(*parts)

    def _on_phase_started(self, _: EventType, payload: BaseModel) -> None:
        p: PhaseStartedPayload = payload  # type: ignore[assignment]
        self._agents.clear()
        self._phase_status[p.phase] = "running"
        self._refresh()

    def _on_phase_completed(self, _: EventType, payload: BaseModel) -> None:
        p: PhaseCompletedPayload = payload  # type: ignore[assignment]
        self._phase_status[p.phase] = "done"
        self._current_tool = None
        self._refresh()

    def _on_agent_started(self, _: EventType, payload: BaseModel) -> None:
        p: AgentStartedPayload = payload  # type: ignore[assignment]
        self._agents[p.task_id] = {
            "name": p.agent_name,
            "model": p.model,
            "files_label": p.files_label,
            "status": "running",
            "current_tool": "",
            "tokens": 0,
            "tool_calls": 0,
        }
        self._refresh()

    def _on_agent_progress(self, _: EventType, payload: BaseModel) -> None:
        p: AgentProgressPayload = payload  # type: ignore[assignment]
        if p.task_id in self._agents:
            self._agents[p.task_id]["tokens"] = p.tokens
            self._agents[p.task_id]["tool_calls"] = p.tool_calls
            self._agents[p.task_id]["current_tool"] = p.current_tool
        self._refresh()

    def _on_agent_completed(self, _: EventType, payload: BaseModel) -> None:
        p: AgentCompletedPayload = payload  # type: ignore[assignment]
        if p.task_id in self._agents:
            self._agents[p.task_id]["status"] = "done"
            self._agents[p.task_id]["tokens"] = p.tokens
        self._cumulative_tokens += p.tokens
        self._refresh()

    def _on_tool_started(self, _: EventType, payload: BaseModel) -> None:
        p: MechanicalToolStartedPayload = payload  # type: ignore[assignment]
        self._current_tool = p.tool
        self._refresh()

    def _on_tool_completed(self, _: EventType, payload: BaseModel) -> None:
        p: MechanicalToolCompletedPayload = payload  # type: ignore[assignment]
        self._current_tool = None
        self._mechanical_tools.append(
            {"tool": p.tool, "findings": p.findings_count, "duration_ms": p.duration_ms}
        )
        self._refresh()

    def _on_triage_ready(self, _: EventType, payload: BaseModel) -> None:
        p: TriageReadyPayload = payload  # type: ignore[assignment]
        self._triage_info = f"{p.findings_count} findings, {p.fixable_count} fixable"
        self._refresh()

    def _on_fix_progress(self, _: EventType, payload: BaseModel) -> None:
        p: FixProgressPayload = payload  # type: ignore[assignment]
        for item in self._fix_files:
            if item["file"] == p.file:
                item["status"] = p.status
                self._refresh()
                return
        self._fix_files.append({"file": p.file, "status": p.status})
        self._refresh()

    def _on_completed(self, _: EventType, payload: BaseModel) -> None:
        self._refresh()
        self.stop()

    def _on_error(self, _: EventType, payload: BaseModel) -> None:
        p: WorkflowErrorPayload = payload  # type: ignore[assignment]
        self._error = p.error
        self._refresh()
        self.stop()
