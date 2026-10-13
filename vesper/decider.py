"""Deterministic gate: Signal or Refusal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Union

from vesper.posterior import BetaPosterior
from vesper.state import MarketState


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Signal:
    side: Side
    size: float
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "SIGNAL",
            "side": self.side.value,
            "size": self.size,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Refusal:
    reason: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "REFUSE",
            "reason": self.reason,
            "confidence": self.confidence,
        }


Decision = Union[Signal, Refusal]


@dataclass
class DeciderConfig:
    min_edge_prob: float = 0.95
    max_spread_bps: float = 5.0
    min_volume: int = 1
    max_size: float = 1.0
    payoff_ratio: float = 1.0
    cost_bps: float = 2.0
    stop_pct: float = 0.005
    explore_ticks: int = 50
    explore_size: float = 0.25
    probe_period: int = 2
    probe_size: float = 0.1


class Decider:
    def __init__(self, cfg: DeciderConfig) -> None:
        self.cfg = cfg
        self.posterior = BetaPosterior()
        self._tick_index = 0

    def _is_probe_tick(self) -> bool:
        if self.cfg.probe_period <= 0:
            return False
        return (self._tick_index % self.cfg.probe_period) == 0

    def decide(self, s: MarketState) -> Decision:
        idx = self._tick_index
        self._tick_index += 1

        if s.spread_bps > self.cfg.max_spread_bps:
            return Refusal("spread too wide", 0.0)
        if s.volume < self.cfg.min_volume:
            return Refusal("volume too low", 0.0)

        if idx < self.cfg.explore_ticks:
            if not s.features or s.features[0] == 0.0:
                return Refusal("explore: no signal", 0.0)
            m = s.features[0]
            return Signal(
                Side.BUY if m > 0 else Side.SELL,
                self.cfg.explore_size,
                0.5,
                "explore",
            )

        if not s.features or s.features[0] == 0.0:
            return Refusal("no signal", 0.0)
        m = s.features[0]

        cost_R = self.cfg.cost_bps / (self.cfg.stop_pct * 10000.0)
        breakeven_p = (1.0 + cost_R) / (1.0 + self.cfg.payoff_ratio)
        p_edge = self.posterior.prob_above(breakeven_p)

        if p_edge < self.cfg.min_edge_prob:
            if self._is_probe_tick():
                return Signal(
                    Side.BUY if m > 0 else Side.SELL,
                    self.cfg.probe_size,
                    p_edge,
                    "probe",
                )
            return Refusal("P(edge>0)=" + str(round(p_edge, 3)), p_edge)

        side = Side.BUY if m > 0 else Side.SELL
        size = round(min(p_edge, self.cfg.max_size), 4)
        return Signal(
            side,
            size,
            p_edge,
            "p_edge=" + str(round(p_edge, 3)) + " mom=" + str(round(m, 3)),
        )

    def learn(self, win: bool) -> None:
        self.posterior.update(win)