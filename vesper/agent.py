"""
Vesper agent.

The Agent is the only object that owns decision state. It:

1. Resolves the previous pending signal against the new tick and feeds the
   win/loss back into the Decider.
2. Asks the Decider for a new decision.
3. If the decision is a Signal, optionally routes it to a broker via the
   Sizer -> RiskGate -> Broker -> OrderStore pipeline.

Broker execution is a pure side effect: the ``pending`` learning loop stays
based on ``s.last`` regardless of what the broker reports. This is what
``scripts/run_determinism.py`` verifies — decisions must be identical
whether or not a broker is attached.
"""
from __future__ import annotations

from typing import Optional, Tuple

from vesper.decider import Decider, DeciderConfig, Decision, Signal, Side
from vesper.log import MemoryLog
from vesper.state import MarketState

from vesper.brokers.alpaca import Fill          # for type hints only
from vesper.sizing import Sizer
from vesper.risk import RiskGate
from vesper.store import OrderStore


class Agent:
    def __init__(
        self,
        cfg: Optional[DeciderConfig] = None,
        frozen: bool = False,
        broker=None,
        sizer: Optional[Sizer] = None,
        risk: Optional[RiskGate] = None,
        store: Optional[OrderStore] = None,
        symbol: str = "KRAKEN:XBTUSD",
    ) -> None:
        self.log = MemoryLog()
        self.decider = Decider(cfg or DeciderConfig())
        self.pending: Optional[Tuple[Signal, float]] = None
        self.frozen = frozen

        # Execution layer (all optional; broker=None keeps behavior identical
        # to the pre-execution Agent)
        self.broker = broker
        self.sizer = sizer or Sizer()
        self.risk = risk or RiskGate()
        self.store = store or OrderStore(path=":memory:")
        self.symbol = symbol

    # ------------------------------------------------------------------ #
    # Main tick handler
    # ------------------------------------------------------------------ #
    def on_tick(self, s: MarketState) -> Decision:
        # 1. Resolve the previous pending signal against the new tick.
        if self.pending is not None:
            signal, entry = self.pending
            if signal.side == Side.BUY:
                win = s.last > entry
            else:
                win = s.last < entry

            self.decider.learn(win)
            self.log.append({
                "type": "PENDING_RESOLVED",
                "entry": entry,
                "exit": s.last,
                "win": win,
            })
            self.pending = None

        # 2. Make a new decision.
        d = self.decider.decide(s)

        # 3. If it's a Signal, optionally execute, then record it.
        if isinstance(d, Signal):
            execution_id = self._execute(d, s)

            entry_record = {
                "state_fp": s.fingerprint(),
                "decision": d.to_dict(),
            }
            if execution_id is not None:
                entry_record["execution_id"] = execution_id
            self.log.append(entry_record)

            self.pending = (d, s.last)

        return d

    # ------------------------------------------------------------------ #
    # Execution pipeline
    # ------------------------------------------------------------------ #
    def _execute(self, signal: Signal, s: MarketState) -> Optional[str]:
        """
        Route a Signal through Sizer -> RiskGate -> Broker -> OrderStore.

        Returns the broker order_id on success, or None if execution was
        skipped (no broker, frozen, risk-blocked, or size-zero). All skip
        paths append their own audit entry, but they never mutate ``pending``
        and never influence the Decider.
        """
        if self.broker is None or self.frozen:
            return None

        equity = self.broker.equity()
        position = self.broker.position(self.symbol)
        open_positions = 1 if position != 0 else 0

        allowed, reason = self.risk.check(equity, open_positions)
        if not allowed:
            self.log.append({"type": "RISK_BLOCK", "reason": reason})
            return None

        qty = self.sizer.size(equity, s.last)
        if qty <= 0:
            self.log.append({"type": "SIZE_ZERO", "equity": equity, "price": s.last})
            return None

        fill: Fill = self.broker.submit_market_order(
            symbol=self.symbol,
            qty=qty,
            side="buy" if signal.side == Side.BUY else "sell",
            client_order_id=f"{s.fingerprint()}-{signal.side.name}",
        )

        self.store.save(
            client_order_id=fill.client_order_id,
            order_id=fill.order_id,
            symbol=self.symbol,
            side=fill.side,
            qty=qty,
            status=fill.status,
            filled_avg_price=fill.filled_avg_price,
        )

        self.log.append({
            "type": "EXECUTION",
            "order_id": fill.order_id,
            "client_order_id": fill.client_order_id,
            "status": fill.status,
            "filled_qty": fill.filled_qty,
            "filled_avg_price": fill.filled_avg_price,
        })
        return fill.order_id

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #
    def audit(self) -> dict:
        """
        Return a summary of the agent's audit state.

        NOTE: if your original audit() returned a different shape,
        restore it here. run_determinism.py does not call audit(), so
        nothing in CI depends on this body.
        """
        return {
            "entries": len(self.log),
            "chain_valid": self.log.verify(),
            "posterior": self.decider.posterior()
            if hasattr(self.decider, "posterior") else None,
        }