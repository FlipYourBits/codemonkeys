from __future__ import annotations

from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    FindingsSummaryPayload,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    TriageReadyPayload,
)


class TestNewEventTypeValues:
    def test_mechanical_tool_started_value(self) -> None:
        assert EventType.MECHANICAL_TOOL_STARTED.value == "mechanical_tool_started"

    def test_mechanical_tool_completed_value(self) -> None:
        assert EventType.MECHANICAL_TOOL_COMPLETED.value == "mechanical_tool_completed"

    def test_findings_summary_value(self) -> None:
        assert EventType.FINDINGS_SUMMARY.value == "findings_summary"

    def test_triage_ready_value(self) -> None:
        assert EventType.TRIAGE_READY.value == "triage_ready"

    def test_fix_progress_value(self) -> None:
        assert EventType.FIX_PROGRESS.value == "fix_progress"


class TestNewPayloads:
    def test_mechanical_tool_started_payload(self) -> None:
        payload = MechanicalToolStartedPayload(tool="ruff", files_count=12)
        assert payload.tool == "ruff"
        assert payload.files_count == 12

    def test_mechanical_tool_completed_payload(self) -> None:
        payload = MechanicalToolCompletedPayload(
            tool="ruff", findings_count=3, duration_ms=450
        )
        assert payload.tool == "ruff"
        assert payload.findings_count == 3
        assert payload.duration_ms == 450

    def test_findings_summary_payload(self) -> None:
        payload = FindingsSummaryPayload(
            total=10,
            by_severity={"high": 2, "medium": 5, "low": 3},
            by_category={"security": 2, "style": 8},
        )
        assert payload.total == 10
        assert payload.by_severity["high"] == 2
        assert payload.by_category["style"] == 8

    def test_triage_ready_payload(self) -> None:
        payload = TriageReadyPayload(findings_count=10, fixable_count=7)
        assert payload.findings_count == 10
        assert payload.fixable_count == 7

    def test_fix_progress_payload(self) -> None:
        payload = FixProgressPayload(file="src/main.py", status="completed")
        assert payload.file == "src/main.py"
        assert payload.status == "completed"

    def test_fix_progress_payload_all_statuses(self) -> None:
        for status in ("started", "completed", "failed"):
            payload = FixProgressPayload(file="x.py", status=status)
            assert payload.status == status


class TestNewEventsEmission:
    def test_emit_mechanical_tool_started(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.MECHANICAL_TOOL_STARTED, handler)
        payload = MechanicalToolStartedPayload(tool="pyright", files_count=5)
        emitter.emit(EventType.MECHANICAL_TOOL_STARTED, payload)

        assert len(received) == 1
        assert received[0][0] == EventType.MECHANICAL_TOOL_STARTED
        assert received[0][1].tool == "pyright"

    def test_emit_mechanical_tool_completed(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.MECHANICAL_TOOL_COMPLETED, handler)
        payload = MechanicalToolCompletedPayload(
            tool="ruff", findings_count=2, duration_ms=100
        )
        emitter.emit(EventType.MECHANICAL_TOOL_COMPLETED, payload)

        assert len(received) == 1
        assert received[0][1].findings_count == 2

    def test_emit_findings_summary(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.FINDINGS_SUMMARY, handler)
        payload = FindingsSummaryPayload(
            total=5, by_severity={"high": 1}, by_category={"lint": 5}
        )
        emitter.emit(EventType.FINDINGS_SUMMARY, payload)

        assert len(received) == 1
        assert received[0][1].total == 5

    def test_emit_triage_ready(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.TRIAGE_READY, handler)
        payload = TriageReadyPayload(findings_count=8, fixable_count=4)
        emitter.emit(EventType.TRIAGE_READY, payload)

        assert len(received) == 1
        assert received[0][1].fixable_count == 4

    def test_emit_fix_progress(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.FIX_PROGRESS, handler)
        payload = FixProgressPayload(file="app.py", status="started")
        emitter.emit(EventType.FIX_PROGRESS, payload)

        assert len(received) == 1
        assert received[0][1].file == "app.py"
        assert received[0][1].status == "started"
