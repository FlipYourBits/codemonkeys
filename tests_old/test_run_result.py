from __future__ import annotations

from codemonkeys.core.run_result import RunResult


class TestRunResult:
    def test_basic_construction(self) -> None:
        r = RunResult(
            text="hello",
            structured={"key": "value"},
            usage={"input_tokens": 100, "output_tokens": 50},
            cost=0.01,
            duration_ms=1234,
        )
        assert r.text == "hello"
        assert r.structured == {"key": "value"}
        assert r.cost == 0.01
        assert r.duration_ms == 1234

    def test_defaults(self) -> None:
        r = RunResult(text="", structured=None, usage={}, cost=None, duration_ms=0)
        assert r.structured is None
        assert r.cost is None
