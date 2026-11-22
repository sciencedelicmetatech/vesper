"""
Startup reconciliation for Vesper execution.

After a crash, OrderStore may hold orders whose true state lives only at
the broker. reconcile() walks every unresolved order, asks the broker
what happened, and updates the store.

Semantics
---------
- Order present at broker  -> overwrite the row with the broker's view
                              (status, filled_qty, filled_avg_price).
- Order unknown at broker  -> mark as "rejected". A client_order_id the
                              broker has never seen means the submission
                              never reached it, so it can never fill.
- Broker raises            -> do NOT mark anything; abort reconciliation
                              and let the caller decide. Guessing here is
                              how real money goes missing.

The function is idempotent: running it twice in a row produces the same
store state and the same audit log tail.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol

from vesper.store import OrderStore


log = logging.getLogger("vesper.reconcile")


class _ReconcilableBroker(Protocol):
    def get_order_by_client_id(self, coid: str): ...
    # Returns a Fill or None


def reconcile(
    broker: _ReconcilableBroker,
    store: OrderStore,
    logger: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Bring OrderStore into agreement with the broker for all in-flight orders.

    Returns a small summary dict for logging / tests:
        {
            "checked":   int,   # unresolved orders visited
            "resolved":  int,   # rows updated with broker-confirmed state
            "rejected":  int,   # rows marked rejected (unknown to broker)
        }

    Raises on broker error — never guesses a terminal state on failure.
    """
    say = logger or log.info

    pending = store.unresolved()
    stats = {"checked": len(pending), "resolved": 0, "rejected": 0}

    if not pending:
        say("reconcile: nothing to do (store clean)")
        return stats

    say(f"reconcile: {len(pending)} unresolved order(s)")

    for coid in pending:
        fill = broker.get_order_by_client_id(coid)

        if fill is None:
            say(f"reconcile: {coid} unknown at broker -> marking rejected")
            store.save(
                client_order_id=coid,
                order_id="",
                symbol="",
                side="",
                qty=0.0,
                status="rejected",
                filled_avg_price=None,
            )
            stats["rejected"] += 1
            continue

        say(
            f"reconcile: {coid} -> status={fill.status} "
            f"filled_qty={fill.filled_qty} "
            f"avg_price={fill.filled_avg_price}"
        )
        store.save(
            client_order_id=coid,
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side,
            qty=fill.filled_qty,
            status=fill.status,
            filled_avg_price=fill.filled_avg_price,
        )
        stats["resolved"] += 1

    say(
        f"reconcile: done checked={stats['checked']} "
        f"resolved={stats['resolved']} rejected={stats['rejected']}"
    )
    return stats