"""Rich CLI progress display for workflow execution.

Subscribes to workflow events and renders a live updating panel showing:
- Phase checklist (pending/running/done)
- Mechanical tool status as they complete
- Fix progress per file
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from codemonkeys.workflows.events import (
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


class WorkflowProgress:
    """Rich live display driven by workflow events."""

    def __init__(self, workflow: Workflow, console: Console | None = None) -> None:
        self._console = console or Console(stderr=True)
        self._phases = [p.name for p in workflow.phases]
        self._phase_status: dict[str, str] = {p: "pending" for p in self._phases}
        self._mechanical_tools: list[dict[str, Any]] = []
        self._current_tool: str | None = None
        self._fix_files: list[dict[str, str]] = []
        self._triage_info: str = ""
        self._error: str | None = None
        self._live: Live | None = None

    def attach(self, emitter: EventEmitter) -> None:
        """Subscribe to all relevant events."""
        emitter.on(EventType.PHASE_STARTED, self._on_phase_started)
        emitter.on(EventType.PHASE_COMPLETED, self._on_phase_completed)
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
            refresh_per_second=8,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Group:
        parts: list[Text | Spinner | Group] = []

        # Phase checklist
        for name in self._phases:
            status = self._phase_status[name]
            line = Text()
            if status == "done":
                line.append("  ✓ ", style="green")
                line.append(name.replace("_", " "), style="green")
            elif status == "running":
                line.append("  ● ", style="yellow")
                line.append(name.replace("_", " "), style="bold yellow")
                line.append("  ⠋", style="yellow")
            else:
                line.append("  ○ ", style="dim")
                line.append(name.replace("_", " "), style="dim")
            parts.append(line)

            # Show mechanical tool details under mechanical_audit
            if (
                name == "mechanical_audit"
                and status == "running"
                and self._current_tool
            ):
                tool_line = Text()
                tool_line.append(f"      running {self._current_tool}...", style="dim")
                parts.append(tool_line)

            if name == "mechanical_audit" and self._mechanical_tools:
                for tool_info in self._mechanical_tools:
                    tool_line = Text()
                    tool_line.append(f"      ✓ {tool_info['tool']}", style="dim green")
                    tool_line.append(
                        f"  {tool_info['findings']} finding{'s' if tool_info['findings'] != 1 else ''}",
                        style="dim",
                    )
                    tool_line.append(f"  {tool_info['duration_ms']}ms", style="dim")
                    parts.append(tool_line)

            # Show triage info
            if name == "triage" and self._triage_info:
                info_line = Text()
                info_line.append(f"      {self._triage_info}", style="dim")
                parts.append(info_line)

            # Show fix progress under fix phase
            if name == "fix" and self._fix_files:
                for fix_info in self._fix_files:
                    fix_line = Text()
                    if fix_info["status"] == "started":
                        fix_line.append(f"      ● {fix_info['file']}", style="yellow")
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
        p = payload
        assert isinstance(p, PhaseStartedPayload)
        self._phase_status[p.phase] = "running"
        self._refresh()

    def _on_phase_completed(self, _: EventType, payload: BaseModel) -> None:
        p = payload
        assert isinstance(p, PhaseCompletedPayload)
        self._phase_status[p.phase] = "done"
        self._current_tool = None
        self._refresh()

    def _on_tool_started(self, _: EventType, payload: BaseModel) -> None:
        p = payload
        assert isinstance(p, MechanicalToolStartedPayload)
        self._current_tool = p.tool
        self._refresh()

    def _on_tool_completed(self, _: EventType, payload: BaseModel) -> None:
        p = payload
        assert isinstance(p, MechanicalToolCompletedPayload)
        self._current_tool = None
        self._mechanical_tools.append(
            {"tool": p.tool, "findings": p.findings_count, "duration_ms": p.duration_ms}
        )
        self._refresh()

    def _on_triage_ready(self, _: EventType, payload: BaseModel) -> None:
        p = payload
        assert isinstance(p, TriageReadyPayload)
        self._triage_info = f"{p.findings_count} findings, {p.fixable_count} fixable"
        self._refresh()

    def _on_fix_progress(self, _: EventType, payload: BaseModel) -> None:
        p = payload
        assert isinstance(p, FixProgressPayload)
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
        p = payload
        assert isinstance(p, WorkflowErrorPayload)
        self._error = p.error
        self._refresh()
        self.stop()
