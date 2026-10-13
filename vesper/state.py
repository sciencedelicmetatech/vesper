"""Immutable market tick."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Tuple


@dataclass(frozen=True)
class MarketState:
    symbol: str
    timestamp: int
    bid: float
    ask: float
    last: float
    volume: int
    features: Tuple[float, ...] = ()

    @property
    def spread_bps(self) -> float:
        if self.last <= 0.0:
            return 1e9
        return (self.ask - self.bid) / self.last * 10000.0

    def fingerprint(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]