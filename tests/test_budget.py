from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentpipe.budget import BudgetTracker


class TestBudgetTracker:
    def test_no_cap_does_not_warn(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=None, on_warn=lambda c, k: warns.append((c, k))
        )
        t.update(99.0)
        assert warns == []
        assert t.last_cost_usd == 99.0

    def test_below_threshold_silent(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=1.0,
            warn_at_pct=0.8,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.79)
        assert warns == []

    def test_at_threshold_fires_once(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=1.0,
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
            max_budget_usd=1.0,
            warn_at_pct=None,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.99)
        assert warns == []
        assert t.last_cost_usd == 0.99

    def test_invalid_pct_raises(self):
        with pytest.raises(ValueError):
            BudgetTracker(max_budget_usd=1.0, warn_at_pct=0.0)
        with pytest.raises(ValueError):
            BudgetTracker(max_budget_usd=1.0, warn_at_pct=1.5)
        with pytest.raises(ValueError):
            BudgetTracker(max_budget_usd=1.0, warn_at_pct=[0.5, 1.5])

    def test_list_of_pcts_each_fires_once(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=1.0,
            warn_at_pct=[0.8, 0.9, 0.95],
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.79)
        t.update(0.85)
        t.update(0.92)
        t.update(0.96)
        t.update(0.99)
        assert warns == [(0.85, 1.0), (0.92, 1.0), (0.96, 1.0)]

    def test_list_unsorted_input_still_ordered(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=1.0,
            warn_at_pct=[0.95, 0.8, 0.9],
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.81)
        t.update(0.91)
        t.update(0.96)
        assert [w[0] for w in warns] == [0.81, 0.91, 0.96]

    def test_single_jump_past_multiple_thresholds_fires_each(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=1.0,
            warn_at_pct=[0.8, 0.9, 0.95],
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.update(0.99)
        assert len(warns) == 3

    def test_observe_reads_total_cost_usd(self):
        warns: list[tuple[float, float]] = []
        t = BudgetTracker(
            max_budget_usd=2.0,
            warn_at_pct=0.5,
            on_warn=lambda c, k: warns.append((c, k)),
        )
        t.observe(SimpleNamespace(total_cost_usd=0.5))
        t.observe(SimpleNamespace(total_cost_usd=1.2))
        assert warns == [(1.2, 2.0)]
        assert t.last_cost_usd == 1.2

    def test_observe_ignores_messages_without_cost(self):
        t = BudgetTracker(max_budget_usd=1.0)
        t.observe(SimpleNamespace(content="hi"))
        assert t.last_cost_usd == 0.0
