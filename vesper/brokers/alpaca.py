import os
import time
import uuid
import httpx
from dataclasses import dataclass
from typing import Optional

BASE = "https://paper-api.alpaca.markets"  # switch to api.alpaca.markets for live

@dataclass
class Fill:
    order_id: str
    client_order_id: str
    status: str            # new, filled, partially_filled, rejected, canceled
    filled_qty: float
    filled_avg_price: Optional[float]
    symbol: str
    side: str

class AlpacaBroker:
    def __init__(self, key: Optional[str] = None, secret: Optional[str] = None,
                 paper: bool = True, timeout: float = 10.0):
        self.key = key or os.environ["ALPACA_KEY"]
        self.secret = secret or os.environ["ALPACA_SECRET"]
        self.base = BASE if paper else "https://api.alpaca.markets"
        self.http = httpx.Client(
            base_url=self.base,
            headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret},
            timeout=timeout,
        )

    def _retry(self, fn, attempts: int = 3, backoff: float = 0.5):
        last = None
        for i in range(attempts):
            try:
                return fn()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last = e
                time.sleep(backoff * (2 ** i))
        raise last

    def submit_market_order(self, symbol: str, qty: float, side: str,
                            client_order_id: Optional[str] = None) -> Fill:
        coid = client_order_id or str(uuid.uuid4())  # idempotency key
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,                 # "buy" | "sell"
            "type": "market",
            "time_in_force": "day",
            "client_order_id": coid,
        }
        r = self._retry(lambda: self.http.post("/v2/orders", json=body))
        r.raise_for_status()
        return self._to_fill(r.json())

    def get_order(self, order_id: str) -> Fill:
        r = self._retry(lambda: self.http.get(f"/v2/orders/{order_id}"))
        r.raise_for_status()
        return self._to_fill(r.json())

    def get_order_by_client_id(self, coid: str) -> Optional[Fill]:
        r = self._retry(lambda: self.http.get("/v2/orders:by_client_order_id",
                                              params={"client_order_id": coid}))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return self._to_fill(r.json())

    def cancel(self, order_id: str) -> bool:
        r = self._retry(lambda: self.http.delete(f"/v2/orders/{order_id}"))
        return r.status_code in (200, 204)

    def position(self, symbol: str) -> float:
        r = self._retry(lambda: self.http.get(f"/v2/positions/{symbol}"))
        if r.status_code == 404:
            return 0.0
        r.raise_for_status()
        return float(r.json()["qty"])

    def equity(self) -> float:
        r = self._retry(lambda: self.http.get("/v2/account"))
        r.raise_for_status()
        return float(r.json()["equity"])

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