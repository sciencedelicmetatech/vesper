"""Tick loop, resolution, learning."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from vesper.decider import Decision, Decider, DeciderConfig, Side, Signal
from vesper.log import MemoryLog
from vesper.state import MarketState


class Agent:
    def __init__(
        self,
        cfg: Optional[DeciderConfig] = None,
        frozen: bool = False,
    ) -> None:
        self.log = MemoryLog()
        self.decider = Decider(cfg or DeciderConfig())
        self.pending: Optional[Tuple[Signal, float]] = None
        self.frozen = frozen

    def on_tick(self, s: MarketState) -> Decision:
        if self.pending is not None:
            sig, entry = self.pending
            exit_price = s.last
            if sig.side == Side.BUY:
                win = exit_price > entry
            else:
                win = exit_price < entry
            if not self.frozen:
                self.decider.learn(win)
            self.log.append(
                {
                    "type": "RESOLVE",
                    "entry": entry,
                    "exit": exit_price,
                    "win": win,
                    "size": sig.size,
                    "posterior_n": self.decider.posterior.n,
                    "posterior_mean": round(self.decider.posterior.mean, 4),
                    "frozen": self.frozen,
                }
            )
            self.pending = None

        d = self.decider.decide(s)
        if isinstance(d, Signal):
            self.pending = (d, s.last)
        self.log.append({"state_fp": s.fingerprint(), "decision": d.to_dict()})
        return d

    def audit(self) -> Dict[str, Any]:
        return {
            "entries": len(self.log),
            "chain_valid": self.log.verify(),
            "head": self.log.head,
            "posterior_n": self.decider.posterior.n,
            "posterior_mean": round(self.decider.posterior.mean, 4),
        }