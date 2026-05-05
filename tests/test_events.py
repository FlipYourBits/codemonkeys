from __future__ import annotations

from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    PhaseStartedPayload,
)


class TestEventEmitter:
    def test_subscribe_and_emit(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.PHASE_STARTED, handler)
        payload = PhaseStartedPayload(phase="discover", workflow="review")
        emitter.emit(EventType.PHASE_STARTED, payload)
        assert len(received) == 1
        assert received[0][0] == EventType.PHASE_STARTED
        assert received[0][1].phase == "discover"

    def test_wildcard_subscriber(self) -> None:
        emitter = EventEmitter()
        received: list[EventType] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append(event_type)

        emitter.on_any(handler)
        emitter.emit(
            EventType.PHASE_STARTED, PhaseStartedPayload(phase="x", workflow="y")
        )
        emitter.emit(
            EventType.AGENT_STARTED, AgentStartedPayload(agent_name="test", task_id="1")
        )
        assert len(received) == 2

    def test_no_subscribers_is_fine(self) -> None:
        emitter = EventEmitter()
        emitter.emit(
            EventType.PHASE_STARTED, PhaseStartedPayload(phase="x", workflow="y")
        )

    def test_agent_payloads(self) -> None:
        started = AgentStartedPayload(agent_name="reviewer", task_id="abc")
        assert started.agent_name == "reviewer"
        completed = AgentCompletedPayload(
            agent_name="reviewer", task_id="abc", tokens=1500
        )
        assert completed.tokens == 1500
