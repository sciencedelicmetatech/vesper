"""
Alpaca broker adapter for Vesper.

Responsibilities
----------------
- Submit market orders (with idempotency via client_order_id)
- Submit bracket orders (take-profit + stop-loss in one shot)
- Query order state, positions, and account equity
- Retry transient network failures with exponential backoff

This module is broker-API-specific. It must not contain any strategy logic.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx


PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"


@dataclass
class Fill:
    """Normalized order result. Every broker adapter must return this."""
    order_id: str
    client_order_id: str
    status: str                      # new | accepted | filled | partially_filled | rejected | canceled
    filled_qty: float
    filled_avg_price: Optional[float]
    symbol: str
    side: str                        # "buy" | "sell"


class AlpacaBroker:
    def __init__(
        self,
        key: Optional[str] = None,
        secret: Optional[str] = None,
        paper: bool = True,
        timeout: float = 10.0,
    ):
        self.key = key or os.environ["ALPACA_KEY"]
        self.secret = secret or os.environ["ALPACA_SECRET"]
        self.base = PAPER_BASE if paper else LIVE_BASE
        self.http = httpx.Client(
            base_url=self.base,
            headers={
                "APCA-API-KEY-ID": self.key,
                "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _retry(self, fn, attempts: int = 3, backoff: float = 0.5):
        last: Optional[Exception] = None
        for i in range(attempts):
            try:
                return fn()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last = e
                time.sleep(backoff * (2 ** i))
        assert last is not None
        raise last

    def _to_fill(self, j: dict) -> Fill:
        return Fill(
            order_id=j["id"],
            client_order_id=j["client_order_id"],
            status=j["status"],
            filled_qty=float(j.get("filled_qty") or 0),
            filled_avg_price=float(j["filled_avg_price"]) if j.get("filled_avg_price") else None,
            symbol=j["symbol"],
            side=j["side"],
        )

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
        coid = client_order_id or str(uuid.uuid4())
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": coid,
        }
        r = self._retry(lambda: self.http.post("/v2/orders", json=body))
        r.raise_for_status()
        return self._to_fill(r.json())

    def submit_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        take_profit_px: float,
        stop_loss_px: float,
        client_order_id: Optional[str] = None,
    ) -> Fill:
        """
        Submit a market entry with attached take-profit and stop-loss legs.
        The broker auto-cancels the OCO pair when one leg fills.
        """
        coid = client_order_id or str(uuid.uuid4())
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "gtc",
            "order_class": "bracket",
            "client_order_id": coid,
            "take_profit": {"limit_price": str(round(take_profit_px, 2))},
            "stop_loss":   {"stop_price":  str(round(stop_loss_px, 2))},
        }
        r = self._retry(lambda: self.http.post("/v2/orders", json=body))
        r.raise_for_status()
        return self._to_fill(r.json())

    def get_order(self, order_id: str) -> Fill:
        r = self._retry(lambda: self.http.get(f"/v2/orders/{order_id}"))
        r.raise_for_status()
        return self._to_fill(r.json())

    def get_order_by_client_id(self, coid: str) -> Optional[Fill]:
        """Returns None if the broker has never seen this client_order_id."""
        r = self._retry(
            lambda: self.http.get(
                "/v2/orders:by_client_order_id",
                params={"client_order_id": coid},
            )
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return self._to_fill(r.json())

    def cancel(self, order_id: str) -> bool:
        r = self._retry(lambda: self.http.delete(f"/v2/orders/{order_id}"))
        return r.status_code in (200, 204)

    # ------------------------------------------------------------------ #
    # Account
    # ------------------------------------------------------------------ #
    def position(self, symbol: str) -> float:
        """Return current signed position size. 0.0 if flat."""
        r = self._retry(lambda: self.http.get(f"/v2/positions/{symbol}"))
        if r.status_code == 404:
            return 0.0
        r.raise_for_status()
        return float(r.json()["qty"])

    def equity(self) -> float:
        r = self._retry(lambda: self.http.get("/v2/account"))
        r.raise_for_status()
        return float(r.json()["equity"])