#!/usr/bin/env python3
"""
Determinism verification for Vesper.

Tests
-----
1. Brokerless run twice        -> audit logs byte-identical
2. MockBroker run twice        -> audit logs byte-identical (execution path stable)
3. Brokerless vs MockBroker    -> decision streams identical
                                  (proves execution is a pure side-effect)

Exit 0 if all pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Adjust these imports if your repo layout differs
from vesper.agent import Agent
from vesper.state import MarketState
from vesper.decider import DeciderConfig, Side
from vesper.brokers.mock import MockBroker
from vesper.brokers.alpaca import Fill
from vesper.sizing import Sizer
from vesper.risk import RiskGate
from vesper.store import OrderStore


# --------------------------------------------------------------------------
# Deterministic fixture ticks
# --------------------------------------------------------------------------
def make_fixture_ticks(n: int = 200, seed: int = 7, start: float = 30_000.0) -> List[MarketState]:
    """Seeded random walk. Same inputs -> same outputs, forever."""
    rng = random.Random(seed)
    ticks: List[MarketState] = []
    price = start
    for i in range(n):
        price *= 1 + rng.uniform(-0.002, 0.002)      # +/-20 bps per tick
        spread = price * 0.0002                       # 2 bps spread
        ticks.append(MarketState(
            symbol="KRAKEN:XBTUSD",
            last=price,
            bid=price - spread / 2,
            ask=price + spread / 2,
            timestamp=1_700_000_000 + i,             # fixed, not time.time()
        ))
    return ticks


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def run_agent(ticks: Iterable[MarketState], broker=None) -> list[dict]:
    """Run a fresh agent over `ticks` and return its audit log."""
    store = OrderStore(path=":memory:")              # never touches disk in tests
    agent = Agent(
        cfg=DeciderConfig(),
        frozen=False,
        broker=broker,
        sizer=Sizer(risk_per_trade=0.01, max_position_pct=0.10),
        risk=RiskGate(max_daily_loss_pct=0.03, max_open_positions=3),
        store=store,
        symbol="KRAKEN:XBTUSD",
    )
    for s in ticks:
        agent.on_tick(s)
    return agent.log.entries()


def decisions_from(log: list[dict]) -> list[dict]:
    """Extract only the decision-bearing entries for cross-broker comparison."""
    keep = {"SIGNAL", "REFUSAL", "PENDING_RESOLVED"}
    out = []
    for e in log:
        t = e.get("type") or ("SIGNAL" if "decision" in e else None)
        if t in keep or "decision" in e:
            out.append({k: v for k, v in e.items()
                        if k not in ("execution", "fill", "execution_id")})
    return out


def log_hash(log: list[dict]) -> str:
    blob = json.dumps(log, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def scripted_fills(n: int) -> List[Fill]:
    """MockBroker fills that vary — they should NOT perturb decisions."""
    return [
        Fill(
            order_id=f"mock-{i}",
            client_order_id=f"auto-{i}",
            status="filled",
            filled_qty=0.01 * (i + 1),
            filled_avg_price=30_000.0 + i * 10,
            symbol="KRAKEN:XBTUSD",
            side="buy" if i % 2 == 0 else "sell",
        )
        for i in range(n)
    ]


def banner(msg: str) -> None:
    print(f"\n=== {msg} ===")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_brokerless_determinism(ticks) -> str:
    banner("Test 1: brokerless run twice -> byte-identical logs")
    a = run_agent(ticks, broker=None)
    b = run_agent(ticks, broker=None)
    if log_hash(a) != log_hash(b):
        fail(f"hashes differ: {log_hash(a)[:12]} vs {log_hash(b)[:12]}")
    print(f"OK  entries={len(a)}  hash={log_hash(a)[:16]}")
    return log_hash(a)


def test_mockbroker_determinism(ticks) -> str:
    banner("Test 2: MockBroker run twice -> byte-identical logs")

    def build():
        return MockBroker(
            scripted_fills=scripted_fills(50),
            fixed_equity=100_000.0,
            fixed_positions={},
        )

    a = run_agent(ticks, broker=build())
    b = run_agent(ticks, broker=build())
    if log_hash(a) != log_hash(b):
        fail(f"hashes differ: {log_hash(a)[:12]} vs {log_hash(b)[:12]}")
    print(f"OK  entries={len(a)}  hash={log_hash(a)[:16]}")
    return log_hash(a)


def test_execution_is_side_effect_free(ticks) -> None:
    banner("Test 3: brokerless vs MockBroker -> identical decision streams")
    brokerless = decisions_from(run_agent(ticks, broker=None))
    with_broker = decisions_from(run_agent(
        ticks,
        broker=MockBroker(scripted_fills=scripted_fills(50),
                          fixed_equity=100_000.0),
    ))
    if len(brokerless) != len(with_broker):
        fail(f"decision count mismatch: {len(brokerless)} vs {len(with_broker)}")
    for i, (x, y) in enumerate(zip(brokerless, with_broker)):
        if x != y:
            fail(f"decision #{i} differs:\n  brokerless={x}\n  brokered={y}")
    print(f"OK  {len(brokerless)} decisions match element-for-element")


# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    ticks = make_fixture_ticks(n=args.ticks, seed=args.seed)

    h1 = test_brokerless_determinism(ticks)
    h2 = test_mockbroker_determinism(ticks)
    test_execution_is_side_effect_free(ticks)

    print("\n=== Summary ===")
    print(f"brokerless hash : {h1}")
    print(f"mockbroker hash : {h2}")
    print("All determinism tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())