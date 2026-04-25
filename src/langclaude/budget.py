"""Budget tracking for Claude Agent SDK runs.

The SDK enforces a hard cap natively via `max_budget_usd`. This module adds
the soft warning layer on top: a one-shot callback when running cost
crosses a configurable percentage of the cap.

The tracker reads `total_cost_usd` from any message that exposes it
(typically the final `ResultMessage`, but the SDK may surface running
totals on intermediate messages in future versions). When the SDK only
reports cost at the end, the warning fires post-hoc — which is still
useful signal that the next run should be tightened.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

WarnCallback = Callable[[float, float], None]


def default_on_warn(cost_usd: float, cap_usd: float) -> None:
    pct = (cost_usd / cap_usd * 100) if cap_usd else 0
    print(
        f"[langclaude] WARNING: spent ${cost_usd:.4f} ({pct:.0f}% of ${cap_usd:.4f} cap)",
        file=sys.stderr,
    )


class BudgetTracker:
    """Tracks running cost and fires a one-shot warning at a threshold.

    Args:
        cap_usd: hard cap (the same value passed to the SDK's max_budget_usd).
            None disables tracking.
        warn_at_pct: fraction of the cap (0..1) at which to fire on_warn.
            None disables the warning while keeping the hard cap.
        on_warn: callback `(cost_usd, cap_usd) -> None`. Defaults to a
            stderr print.
    """

    def __init__(
        self,
        *,
        cap_usd: float | None,
        warn_at_pct: float | None = 0.8,
        on_warn: WarnCallback | None = None,
    ) -> None:
        if warn_at_pct is not None and not 0.0 < warn_at_pct <= 1.0:
            raise ValueError(
                f"warn_at_pct must be in (0, 1], got {warn_at_pct}"
            )
        self.cap_usd = cap_usd
        self._threshold = (
            cap_usd * warn_at_pct
            if (cap_usd is not None and warn_at_pct is not None)
            else None
        )
        self._on_warn = on_warn or default_on_warn
        self._warned = False
        self.last_cost_usd: float = 0.0

    def observe(self, message: Any) -> None:
        """Update from a message that may carry total_cost_usd."""
        cost = getattr(message, "total_cost_usd", None)
        if cost is None:
            return
        self.update(float(cost))

    def update(self, cost_usd: float) -> None:
        self.last_cost_usd = cost_usd
        if self._warned or self._threshold is None or self.cap_usd is None:
            return
        if cost_usd >= self._threshold:
            self._on_warn(cost_usd, self.cap_usd)
            self._warned = True
