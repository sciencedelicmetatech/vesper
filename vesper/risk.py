"""
Risk gate for Vesper execution.

The RiskGate is the last line of defense between a Signal and an order.
It answers one question: "is the account allowed to open a new position
right now?" If not, it returns a reason string that the audit log records.

Three checks, evaluated in order:

1. Kill switch    - manually set ``halted = True`` to freeze the account.
2. Daily loss     - halt for the rest of the day if equity has drawn down
                    past ``max_daily_loss_pct`` from the day's starting equity.
3. Position cap   - refuse if ``open_positions >= max_open_positions``.

The gate resets the loss halt at the start of each calendar day, so a bad
Tuesday does not prevent trading on Wednesday.

Determinism note
----------------
``check()`` uses ``date.today()`` by default. For replay or determinism
tests that must be independent of wall-clock time, pass an explicit
``now=dt.date(YYYY, MM, DD)``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RiskGate:
    max_daily_loss_pct: float = 0.03
    """Halt for the rest of the day if equity drops this far from start-of-day."""

    max_open_positions: int = 3
    """Refuse new entries once this many positions are already open."""

    # Public kill switch. Set to True to freeze trading immediately.
    halted: bool = False

    # Internal day-tracking state. Do not set these directly.
    _day: dt.date = field(default_factory=dt.date.today)
    _day_start_equity: float = 0.0

    def check(
        self,
        equity: float,
        open_positions: int,
        now: Optional[dt.date] = None,
    ) -> tuple[bool, str]:
        """
        Return ``(allowed, reason)``.

        ``allowed=False`` means: do not execute this signal. The reason is
        for the audit log only; it must never influence sizing, decision
        logic, or learning.
        """
        today = now or dt.date.today()

        # Roll the day if the calendar has changed. This also clears any
        # halt from a previous day.
        if today != self._day:
            self._day = today
            self._day_start_equity = equity
            self.halted = False

        # First call of the process, or first of a new day after a cold
        # start: anchor the day-start equity. Guard against equity <= 0.
        if self._day_start_equity <= 0:
            self._day_start_equity = max(equity, 0.0)

        # Check 1: kill switch
        if self.halted:
            return False, "halted"

        # Check 2: daily loss limit
        if self._day_start_equity > 0:
            floor = self._day_start_equity * (1.0 - self.max_daily_loss_pct)
            if equity <= floor:
                self.halted = True
                return False, "daily_loss_limit"

        # Check 3: position cap
        if open_positions >= self.max_open_positions:
            return False, "max_positions"

        return True, "ok"

    # ------------------------------------------------------------------ #
    # Operational controls
    # ------------------------------------------------------------------ #
    def halt(self) -> None:
        """Freeze trading immediately. Only ``resume()`` clears this."""
        self.halted = True

    def resume(self) -> None:
        """
        Manual resume. Only call after reconciling broker state — otherwise
        the agent may act on a stale view of positions and equity.
        """
        self.halted = False
        self._day_start_equity = 0.0  # re-anchor on the next check()