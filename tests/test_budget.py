from __future__ import annotations

from types import SimpleNamespace

import pytest

from langclaude.budget import BudgetTracker


class TestBudgetTracker:
    def test_no_cap_does_not_warn(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(cap_usd=None, on_warn=lambda c, k: warns.append((c, k)))
        t.update(99.0)
        assert warns == []
        assert t.last_cost_usd == 99.0

    def test_below_threshold_silent(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            cap_usd=1.0,
            warn_at_pct=0.8,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.79)
        assert warns == []

    def test_at_threshold_fires_once(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            cap_usd=1.0,
            warn_at_pct=0.8,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.80)
        t.update(0.85)
        t.update(0.95)
        assert warns == [(0.80, 1.0)]

    def test_warn_disabled_with_none(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            cap_usd=1.0,
            warn_at_pct=None,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.99)
        assert warns == []
        assert t.last_cost_usd == 0.99

    def test_invalid_pct_raises(self):
        with pytest.raises(ValueError):
            BudgetTracker(cap_usd=1.0, warn_at_pct=0.0)
        with pytest.raises(ValueError):
            BudgetTracker(cap_usd=1.0, warn_at_pct=1.5)

    def test_observe_reads_total_cost_usd(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            cap_usd=2.0,
            warn_at_pct=0.5,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.observe(SimpleNamespace(total_cost_usd=0.5))
        t.observe(SimpleNamespace(total_cost_usd=1.2))
        assert warns == [(1.2, 2.0)]
        assert t.last_cost_usd == 1.2

    def test_observe_ignores_messages_without_cost(self):
        t = BudgetTracker(cap_usd=1.0)
        t.observe(SimpleNamespace(content="hi"))
        assert t.last_cost_usd == 0.0
