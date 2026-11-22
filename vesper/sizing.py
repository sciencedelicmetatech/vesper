"""
Position sizing for Vesper execution.

The Decider emits Signals with an abstract ``size``. For live execution
that number is meaningless without context: what matters is how much of
*this account* to risk. ``Sizer`` answers that question.

Design principles
-----------------
- Risk-first: size is derived from the dollar amount the account is willing
  to lose if the stop is hit, divided by the stop distance in dollars.
- Hard cap: regardless of risk math, no single position may exceed
  ``max_position_pct`` of equity.
- Pure function of (equity, price) -> qty. No broker calls, no state, no
  randomness. Same inputs always produce the same output — required by
  ``scripts/run_determinism.py``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sizer:
    """Convert equity + price into an order quantity."""

    risk_per_trade: float = 0.01
    """Fraction of equity risked per trade (0.01 = 1%)."""

    max_position_pct: float = 0.10
    """Hard cap: no position may exceed this fraction of equity."""

    stop_distance_pct: float = 0.02
    """Assumed stop distance as a fraction of entry price (0.02 = 2%)."""

    min_qty: float = 0.0
    """Below this, return 0.0 (refuse to trade dust)."""

    def size(self, equity: float, price: float) -> float:
        """
        Return the quantity to trade, or 0.0 if the trade should be skipped.

        Parameters
        ----------
        equity : float
            Current account equity in quote currency. Must be > 0.
        price : float
            Current market price of the instrument. Must be > 0.

        Returns
        -------
        float
            Non-negative quantity. Zero means "skip this trade" — the
            caller treats that as a soft refusal, not an error.
        """
        if equity <= 0 or price <= 0:
            return 0.0
        if self.stop_distance_pct <= 0:
            raise ValueError("stop_distance_pct must be > 0")
        if self.risk_per_trade < 0 or self.max_position_pct < 0:
            raise ValueError("risk_per_trade and max_position_pct must be >= 0")

        # Risk-based size: units such that
        #     qty * price * stop_distance_pct == equity * risk_per_trade
        risk_dollars = equity * self.risk_per_trade
        size_by_risk = risk_dollars / (price * self.stop_distance_pct)

        # Cap-based size: never exceed max_position_pct of equity
        size_by_cap = (equity * self.max_position_pct) / price

        qty = min(size_by_risk, size_by_cap)

        if qty < self.min_qty:
            return 0.0
        return round(qty, 8)