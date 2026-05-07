"""Workflow state machine — runs phases sequentially, pauses at gates."""

from __future__ import annotations

import asyncio
from typing import Any

from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    WaitingForUserPayload,
    WorkflowCompletedPayload,
    WorkflowErrorPayload,
)
from codemonkeys.workflows.phases import PhaseType, Workflow, WorkflowContext


class WorkflowEngine:
    def __init__(self, emitter: EventEmitter) -> None:
        self._emitter = emitter
        self._gate_future: asyncio.Future[Any] | None = None

    async def run(self, workflow: Workflow, context: WorkflowContext) -> None:
        context.emitter = self._emitter
        try:
            for phase in workflow.phases:
                self._emitter.emit(
                    EventType.PHASE_STARTED,
                    PhaseStartedPayload(phase=phase.name, workflow=workflow.name),
                )

                if phase.phase_type == PhaseType.GATE:
                    loop = asyncio.get_running_loop()
                    self._gate_future = loop.create_future()
                    self._emitter.emit(
                        EventType.WAITING_FOR_USER,
                        WaitingForUserPayload(phase=phase.name, workflow=workflow.name),
                    )
                    context.user_input = await self._gate_future
                    self._gate_future = None

                result = await phase.execute(context)
                context.phase_results[phase.name] = result

                self._emitter.emit(
                    EventType.PHASE_COMPLETED,
                    PhaseCompletedPayload(phase=phase.name, workflow=workflow.name),
                )

            if getattr(context.config, "graph", False):
                from codemonkeys.workflows.graph import generate_workflow_graph

                generate_workflow_graph(workflow, context)

            self._emitter.emit(
                EventType.WORKFLOW_COMPLETED,
                WorkflowCompletedPayload(workflow=workflow.name, run_id=context.run_id),
            )
        except Exception as exc:
            self._emitter.emit(
                EventType.WORKFLOW_ERROR,
                WorkflowErrorPayload(workflow=workflow.name, error=str(exc)),
            )
            raise

    def resolve_gate(self, user_input: Any) -> None:
        if self._gate_future and not self._gate_future.done():
            self._gate_future.set_result(user_input)
