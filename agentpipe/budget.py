"""Budget tracking for Claude Agent SDK runs.

The SDK can enforce a hard cap natively via `max_budget_usd`. This module
adds a soft warning layer on top: one-shot callbacks at one or more
configurable percentages of the cap.

The tracker reads `total_cost_usd` from any message that exposes it
(typically the final `ResultMessage`, but the SDK may surface running
totals on intermediate messages in future versions). When the SDK only
reports cost at the end, warnings fire post-hoc — which is still useful
signal that the next run should be tightened.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any

WarnCallback = Callable[[float, float], None]


def default_on_warn(
    cost_usd: float, max_budget_usd: float, *, display: Any | None = None
) -> None:
    pct = (cost_usd / max_budget_usd * 100) if max_budget_usd else 0
    msg = f"spent ${cost_usd:.4f} ({pct:.0f}% of ${max_budget_usd:.4f} cap)"
    if display is not None:
        display.warn(msg)
    else:
        print(f"[agentpipe] WARNING: {msg}", file=sys.stderr)


def _normalize_pcts(
    warn_at_pct: float | Sequence[float] | None,
) -> list[float]:
    if warn_at_pct is None:
        return []
    if isinstance(warn_at_pct, (int, float)):
        pcts = [float(warn_at_pct)]
    else:
        pcts = [float(p) for p in warn_at_pct]
    for p in pcts:
        if not 0.0 < p <= 1.0:
            raise ValueError(f"warn_at_pct entries must be in (0, 1], got {p}")
    pcts.sort()
    return pcts


class BudgetTracker:
    """Tracks running cost and fires one-shot warnings at thresholds.

    Args:
        max_budget_usd: hard cap (the same value passed to the SDK's max_budget_usd
            when used). None disables tracking.
        warn_at_pct: a single fraction in (0, 1] or a sequence of fractions
            at which to fire on_warn. None disables warnings.
        on_warn: callback `(cost_usd, max_budget_usd) -> None`. Defaults to a
            stderr print.
    """

    def __init__(
        self,
        *,
        max_budget_usd: float | None,
        warn_at_pct: float | Sequence[float] | None = 0.8,
        on_warn: WarnCallback | None = None,
    ) -> None:
        pcts = _normalize_pcts(warn_at_pct)
        self.max_budget_usd = max_budget_usd
        self._thresholds: list[float] = (
            [max_budget_usd * p for p in pcts] if max_budget_usd is not None else []
        )
        self._on_warn = on_warn or default_on_warn
        self._fired = [False] * len(self._thresholds)
        self.last_cost_usd: float = 0.0

    def observe(self, message: Any) -> None:
        """Update from a message that may carry total_cost_usd."""
        cost = getattr(message, "total_cost_usd", None)
        if cost is None:
            return
        self.update(float(cost))

    def update(self, cost_usd: float) -> None:
        self.last_cost_usd = cost_usd
        if self.max_budget_usd is None:
            return
        for i, threshold in enumerate(self._thresholds):
            if not self._fired[i] and cost_usd >= threshold:
                self._on_warn(cost_usd, self.max_budget_usd)
                self._fired[i] = True
