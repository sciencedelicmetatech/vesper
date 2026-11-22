"""
MockBroker — a fully deterministic broker adapter for tests.

Two modes of operation
----------------------
1. Scripted fills:
       MockBroker(scripted_fills=[Fill(...), Fill(...)])
   Each submit_market_order call pops the next scripted fill, in order.
   Raises if the script runs out (so tests fail loudly instead of silently).

2. Response hook:
       MockBroker(response_fn=lambda sym, qty, side, coid: Fill(...))
   Lets a test generate fills based on the order itself, for scenario
   testing (e.g., "reject the 3rd order").

Determinism guarantees
----------------------
- No use of time, random, or environment.
- Idempotent by client_order_id: replaying the same coid returns the same Fill.
- Every call is recorded in `.calls` for post-hoc assertion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from vesper.brokers.alpaca import Fill


@dataclass
class MockBroker:
    # Mode 1: scripted fills returned in order
    scripted_fills: List[Fill] = field(default_factory=list)

    # Mode 2: function to build a fill from an order request
    response_fn: Optional[Callable[[str, float, str, str], Fill]] = None

    # Fixed account state (tests set these; they never change mid-run)
    fixed_equity: float = 100_000.0
    fixed_positions: Dict[str, float] = field(default_factory=dict)

    # Internal state
    _cursor: int = 0
    _calls: List[dict] = field(default_factory=list)
    _by_coid: Dict[str, Fill] = field(default_factory=dict)
    _orders: Dict[str, Fill] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Orders
    # ------------------------------------------------------------------ #
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        client_order_id: Optional[str] = None,
    ) -> Fill:
        coid = client_order_id or f"mock-{len(self._calls)}"
        self._calls.append({
            "kind": "market",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "client_order_id": coid,
        })

        # Idempotency: same coid -> same fill
        if coid in self._by_coid:
            return self._by_coid[coid]

        fill = self._build_fill(symbol, qty, side, coid)
        self._by_coid[coid] = fill
        self._orders[fill.order_id] = fill
        return fill

    def submit_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        take_profit_px: float,
        stop_loss_px: float,
        client_order_id: Optional[str] = None,
    ) -> Fill:
        coid = client_order_id or f"mock-{len(self._calls)}"
        self._calls.append({
            "kind": "bracket",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "take_profit_px": take_profit_px,
            "stop_loss_px": stop_loss_px,
            "client_order_id": coid,
        })

        if coid in self._by_coid:
            return self._by_coid[coid]

        fill = self._build_fill(symbol, qty, side, coid)
        self._by_coid[coid] = fill
        self._orders[fill.order_id] = fill
        return fill

    def get_order(self, order_id: str) -> Fill:
        if order_id not in self._orders:
            raise KeyError(f"MockBroker has no order {order_id!r}")
        return self._orders[order_id]

    def get_order_by_client_id(self, coid: str) -> Optional[Fill]:
        return self._by_coid.get(coid)

    def cancel(self, order_id: str) -> bool:
        return order_id in self._orders

    # ------------------------------------------------------------------ #
    # Account (static in mock)
    # ------------------------------------------------------------------ #
    def position(self, symbol: str) -> float:
        return self.fixed_positions.get(symbol, 0.0)

    def equity(self) -> float:
        return self.fixed_equity

    # ------------------------------------------------------------------ #
    # Introspection helpers for tests
    # ------------------------------------------------------------------ #
    @property
    def calls(self) -> List[dict]:
        """Read-only view of every order request this broker received."""
        return list(self._calls)

    def reset(self) -> None:
        self._cursor = 0
        self._calls.clear()
        self._by_coid.clear()
        self._orders.clear()

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _build_fill(self, symbol: str, qty: float, side: str, coid: str) -> Fill:
        if self.response_fn is not None:
            return self.response_fn(symbol, qty, side, coid)

        if self._cursor >= len(self.scripted_fills):
            raise RuntimeError(
                f"MockBroker ran out of scripted fills "
                f"(requested #{self._cursor + 1}, have {len(self.scripted_fills)})"
            )

        proto = self.scripted_fills[self._cursor]
        self._cursor += 1

        # Override the coid so idempotency works even if the script
        # didn't bother setting it
        return Fill(
            order_id=proto.order_id,
            client_order_id=coid,
            status=proto.status,
            filled_qty=proto.filled_qty,
            filled_avg_price=proto.filled_avg_price,
            symbol=proto.symbol or symbol,
            side=proto.side or side,
        )