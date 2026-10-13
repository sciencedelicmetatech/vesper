"""Data sources: real fetch with SSL tolerance, plus synthetic fallback."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
import os
import random
import ssl
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from vesper.state import MarketState


def _http_get(url: str, timeout: float = 15.0) -> Optional[bytes]:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        ctx = None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "vesper/1.0 (research)"}
        )
        if ctx is not None:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _enrich(
    rows: List[Dict[str, Any]], symbol: str, window: int = 5
) -> List[MarketState]:
    if len(rows) < 100:
        return []
    prices = [r["last"] for r in rows]
    out: List[MarketState] = []
    for i, r in enumerate(rows):
        feat: Tuple[float, ...] = (
            (0.0,) if i < window else (prices[i] - prices[i - window],)
        )
        out.append(
            MarketState(
                symbol=symbol,
                timestamp=r["timestamp"],
                bid=r["bid"],
                ask=r["ask"],
                last=r["last"],
                volume=r["volume"],
                features=feat,
            )
        )
    return out


def fetch_kraken(pair: str = "XBTUSD", interval: int = 1) -> Optional[List[MarketState]]:
    """Kraken public OHLC. No API key needed."""
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
    data = _http_get(url, timeout=20.0)
    if not data:
        return None
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
        if obj.get("error"):
            return None
        series = None
        for k, v in obj.get("result", {}).items():
            if k != "last" and isinstance(v, list) and v:
                series = v
                break
        if not series or len(series) < 100:
            return None
        rows: List[Dict[str, Any]] = []
        for e in series:
            close = float(e[4])
            if close <= 0:
                continue
            spread = close * 0.0001
            rows.append(
                {
                    "timestamp": int(e[0]),
                    "bid": close - spread / 2.0,
                    "ask": close + spread / 2.0,
                    "last": close,
                    "volume": max(1, int(float(e[6]))) if len(e) > 6 else 1000,
                }
            )
        return _enrich(rows, f"KRAKEN:{pair}")
    except Exception:
        return None


def fetch_stooq(symbol: str = "eurusd") -> Optional[List[MarketState]]:
    """stooq.com daily CSV. HTTP fallback if HTTPS fails."""
    data = None
    for scheme in ("https", "http"):
        data = _http_get(f"{scheme}://stooq.com/q/d/l/?s={symbol}&i=d", timeout=15.0)
        if data and len(data) > 500:
            break
        data = None
    if not data:
        return None
    try:
        rows: List[Dict[str, Any]] = []
        for row in csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace"))):
            try:
                close = float(row["Close"])
            except (KeyError, ValueError):
                continue
            if close <= 0:
                continue
            spread = close * 0.0001
            vol = 1000
            try:
                vol = max(1, int(float(row.get("Volume", "1000"))))
            except (ValueError, TypeError):
                pass
            rows.append(
                {
                    "timestamp": len(rows),
                    "bid": close - spread / 2.0,
                    "ask": close + spread / 2.0,
                    "last": close,
                    "volume": vol,
                }
            )
        return _enrich(rows, f"STOOQ:{symbol.upper()}")
    except Exception:
        return None


def fetch_binance(
    symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 1000
) -> Optional[List[MarketState]]:
    """Binance public klines. No key needed."""
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval={interval}&limit={limit}"
    )
    data = _http_get(url, timeout=20.0)
    if not data:
        return None
    try:
        rows_json = json.loads(data.decode("utf-8", errors="replace"))
        if not isinstance(rows_json, list) or len(rows_json) < 100:
            return None
        rows: List[Dict[str, Any]] = []
        for r in rows_json:
            close = float(r[4])
            if close <= 0:
                continue
            spread = close * 0.0001
            rows.append(
                {
                    "timestamp": int(r[0]),
                    "bid": close - spread / 2.0,
                    "ask": close + spread / 2.0,
                    "last": close,
                    "volume": max(1, int(float(r[5]))) if len(r) > 5 else 1000,
                }
            )
        return _enrich(rows, symbol)
    except Exception:
        return None


def load_local_csv() -> Optional[List[MarketState]]:
    """Parse a local CSV with flexible column names."""
    candidates = [
        "ticks.csv",
        "data/ticks.csv",
        "market.csv",
        "data.csv",
        "EURUSD.csv",
        "BTCUSD.csv",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
            text = data.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                continue
            col_map = {c.strip().lower(): c for c in reader.fieldnames}

            def find(*names: str) -> Optional[str]:
                for n in names:
                    if n in col_map:
                        return col_map[n]
                return None

            last_c = find("last", "price", "close", "mid")
            bid_c = find("bid", "bidprice") or last_c
            ask_c = find("ask", "askprice") or last_c
            vol_c = find("volume", "vol")
            ts_c = find("timestamp", "time", "date", "ts")
            if not last_c:
                continue

            rows: List[Dict[str, Any]] = []
            for i, row in enumerate(reader):
                try:
                    last = float(row[last_c])
                    if last <= 0:
                        continue
                    bid = float(row[bid_c]) if bid_c else last
                    ask = float(row[ask_c]) if ask_c else last
                    if bid <= 0 or ask <= 0:
                        continue
                    if ask < bid:
                        bid, ask = ask, bid
                    vol = max(1, int(float(row[vol_c]))) if vol_c else 1000
                    ts = i
                    if ts_c:
                        try:
                            ts = int(float(row[ts_c]))
                        except (ValueError, TypeError):
                            ts = i
                    rows.append(
                        {
                            "timestamp": ts,
                            "bid": bid,
                            "ask": ask,
                            "last": last,
                            "volume": vol,
                        }
                    )
                except (KeyError, ValueError, TypeError):
                    continue
            ticks = _enrich(rows, f"LOCAL:{os.path.basename(path)}")
            if ticks:
                return ticks
        except (IOError, OSError, csv.Error):
            continue
    return None


def _student_t(rng: random.Random, df: float) -> float:
    g = rng.gauss(0.0, 1.0)
    chi2 = sum(rng.gauss(0.0, 1.0) ** 2 for _ in range(int(df)))
    return g / math.sqrt(chi2 / df) if chi2 > 0 else 0.0


def make_ticks_realistic(n: int, seed: int, edge: float) -> List[MarketState]:
    """Synthetic: fat tails (Student-t) + 4 volatility regimes."""
    rng = random.Random(seed)
    ticks: List[MarketState] = []
    price = 100.0
    base_ts = 1700000000000
    prev_drift = 0.0
    regime_len = n // 4
    vol_mult = [1.0, 0.5, 2.0, 1.5]
    MIN_PRICE = 1.0
    for i in range(n):
        regime = min(3, i // max(1, regime_len))
        vm = vol_mult[regime]
        noise = _student_t(rng, 3.0) * 0.5 * vm
        drift = noise + edge * prev_drift
        price = round(price + drift, 2)
        if price < MIN_PRICE:
            price = MIN_PRICE
        ticks.append(
            MarketState(
                symbol="SYNTHETIC",
                timestamp=base_ts + i * 1000,
                bid=round(price - 0.01, 2),
                ask=round(price + 0.01, 2),
                last=price,
                volume=rng.randint(500, 5000),
                features=(drift,),
            )
        )
        prev_drift = drift
    return ticks


def acquire() -> Tuple[str, Optional[List[MarketState]]]:
    """Try real sources in order. Return (source_name, ticks_or_None)."""
    for name, fn in (
        ("kraken", lambda: fetch_kraken()),
        ("stooq", lambda: fetch_stooq()),
        ("binance", lambda: fetch_binance()),
    ):
        ticks = fn()
        if ticks:
            return name, ticks
    local = load_local_csv()
    if local:
        return "local_csv", local
    return "synthetic", None