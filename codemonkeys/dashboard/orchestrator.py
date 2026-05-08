"""Agent orchestrator — manages concurrent runs with a bounded pool."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Awaitable

from codemonkeys.core.events import AgentCompleted, Event, EventHandler
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import AgentDefinition, RunResult, json_safe


RunAgentFn = Callable[..., Awaitable[RunResult]]


class Orchestrator:
    """Manages concurrent agent runs with a max-concurrency pool."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._max_concurrent = max_concurrent
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._queue: list[tuple[str, AgentDefinition, str]] = []
        self._run_agent_fn: RunAgentFn = run_agent
        self._event_listeners: list[Callable[[str, dict], None]] = []
        self._active_count = 0

    def add_event_listener(self, listener: Callable[[str, dict], None]) -> None:
        """Register a callback that receives (run_id, event_data) for every event."""
        self._event_listeners.append(listener)

    def _emit_ws_event(self, run_id: str, event: Event) -> None:
        """Broadcast an event to all registered listeners."""
        data = json_safe(event)
        if isinstance(event, AgentCompleted) and isinstance(data.get("result"), dict):
            result = data["result"]
            result.pop("events", None)
            result.pop("agent_def", None)
        event_data = {
            "run_id": run_id,
            "event_type": type(event).__name__,
            "agent_name": event.agent_name,
            "data": data,
            "timestamp": event.timestamp,
        }
        for listener in self._event_listeners:
            listener(run_id, event_data)

    async def submit(self, agent: AgentDefinition, prompt: str) -> str:
        """Submit an agent run. Returns the run_id immediately."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        self._runs[run_id] = {
            "run_id": run_id,
            "agent_name": agent.name,
            "model": agent.model,
            "status": "queued",
            "cost_usd": 0.0,
            "tokens": {"input": 0, "output": 0},
            "current_tool": None,
            "events": [],
            "result": None,
            "started_at": None,
            "completed_at": None,
        }

        if self._active_count < self._max_concurrent:
            self._start_run(run_id, agent, prompt)
        else:
            self._queue.append((run_id, agent, prompt))

        return run_id

    def _start_run(self, run_id: str, agent: AgentDefinition, prompt: str) -> None:
        """Transition a run from queued to running and create its asyncio task."""
        self._active_count += 1
        self._runs[run_id]["status"] = "running"
        self._runs[run_id]["started_at"] = time.time()

        def on_event(event: Event) -> None:
            self._emit_ws_event(run_id, event)

        task = asyncio.create_task(self._execute(run_id, agent, prompt, on_event))
        self._tasks[run_id] = task

    async def _execute(
        self,
        run_id: str,
        agent: AgentDefinition,
        prompt: str,
        on_event: EventHandler,
    ) -> None:
        """Run the agent and update state on completion or failure."""
        try:
            result = await self._run_agent_fn(agent, prompt, on_event=on_event)
            if self._runs[run_id]["status"] == "cancelled":
                return
            self._runs[run_id]["status"] = "completed" if not result.error else "error"
            self._runs[run_id]["result"] = result
            self._runs[run_id]["cost_usd"] = result.cost_usd
            self._runs[run_id]["tokens"] = {
                "input": result.usage.input_tokens,
                "output": result.usage.output_tokens,
            }
            self._runs[run_id]["completed_at"] = time.time()
        except asyncio.CancelledError:
            self._runs[run_id]["status"] = "cancelled"
        except Exception as exc:
            self._runs[run_id]["status"] = "error"
            self._runs[run_id]["result"] = str(exc)
            self._runs[run_id]["completed_at"] = time.time()
        finally:
            self._active_count -= 1
            self._tasks.pop(run_id, None)
            self._drain_queue()

    def _drain_queue(self) -> None:
        """Start queued runs until the concurrency limit is reached."""
        while self._queue and self._active_count < self._max_concurrent:
            run_id, agent, prompt = self._queue.pop(0)
            if self._runs[run_id]["status"] == "cancelled":
                continue
            self._start_run(run_id, agent, prompt)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the state dict for a single run, or None if not found."""
        return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        """Return state dicts for all runs."""
        return list(self._runs.values())

    def cancel(self, run_id: str) -> bool:
        """Cancel a run. Returns True if the run was cancelled, False otherwise."""
        state = self._runs.get(run_id)
        if state is None:
            return False
        if state["status"] == "queued":
            state["status"] = "cancelled"
            self._queue = [(rid, a, p) for rid, a, p in self._queue if rid != run_id]
            return True
        if state["status"] == "running":
            task = self._tasks.get(run_id)
            if task:
                task.cancel()
            state["status"] = "cancelled"
            return True
        return False

    def kill_all(self) -> None:
        """Cancel all queued and running runs."""
        for run_id, _agent, _prompt in self._queue:
            self._runs[run_id]["status"] = "cancelled"
        self._queue.clear()
        for run_id, task in list(self._tasks.items()):
            task.cancel()
            self._runs[run_id]["status"] = "cancelled"
