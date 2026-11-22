"""
Order persistence for Vesper execution.

After a crash, the agent must be able to answer: "which orders did I submit
that the broker might still be working on?" The OrderStore is the source of
truth for that question.

Design principles
-----------------
- Append-or-update, never delete: every order goes through a lifecycle
  (new -> accepted -> filled / rejected / canceled). Each state transition
  overwrites the row but preserves the original ``created_at``.
- Broker-agnostic: stores whatever the adapter's ``Fill`` provides, no more.
- Deterministic tests: the store accepts ``path=":memory:"`` so the
  determinism script never touches disk.
"""
from __future__ import annotations

import sqlite3
import time
from typing import List, Optional


UNRESOLVED_STATUSES = (
    "new",
    "accepted",
    "pending",
    "partially_filled",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    client_order_id  TEXT PRIMARY KEY,
    order_id         TEXT NOT NULL DEFAULT '',
    symbol           TEXT NOT NULL DEFAULT '',
    side             TEXT NOT NULL DEFAULT '',
    qty              REAL NOT NULL DEFAULT 0.0,
    status           TEXT NOT NULL,
    filled_avg_price REAL,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);
"""


class OrderStore:
    """SQLite-backed persistence of submitted orders."""

    def __init__(self, path: str = "vesper_orders.db") -> None:
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def save(
        self,
        client_order_id: str,
        order_id: str,
        symbol: str,
        side: str,
        qty: float,
        status: str,
        filled_avg_price: Optional[float],
    ) -> None:
        """
        Insert or update a single order.

        Idempotent: calling twice with the same arguments is a no-op
        except for ``updated_at``. ``created_at`` is preserved across
        updates, so the unresolved() ordering is stable.
        """
        now = time.time()
        self.db.execute(
            """
            INSERT INTO orders (
                client_order_id, order_id, symbol, side, qty, status,
                filled_avg_price, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_order_id) DO UPDATE SET
                order_id         = excluded.order_id,
                symbol           = excluded.symbol,
                side             = excluded.side,
                qty              = excluded.qty,
                status           = excluded.status,
                filled_avg_price = excluded.filled_avg_price,
                updated_at       = excluded.updated_at
            """,
            (
                client_order_id,
                order_id or "",
                symbol or "",
                side or "",
                float(qty) if qty is not None else 0.0,
                status,
                filled_avg_price,
                now,
                now,
            ),
        )
        self.db.commit()

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def unresolved(self) -> List[str]:
        """
        Return client_order_ids of orders that have not reached a terminal
        state. Reconcile iterates over these on startup.

        Ordered deterministically so that two runs that crashed with the
        same in-flight orders will reconcile in the same order.
        """
        placeholders = ",".join("?" for _ in UNRESOLVED_STATUSES)
        rows = self.db.execute(
            f"SELECT client_order_id FROM orders "
            f"WHERE status IN ({placeholders}) "
            f"ORDER BY created_at ASC, client_order_id ASC",
            UNRESOLVED_STATUSES,
        ).fetchall()
        return [row[0] for row in rows]

    def get(self, client_order_id: str) -> Optional[sqlite3.Row]:
        """Fetch a single order row, or None if never seen."""
        return self.db.execute(
            "SELECT * FROM orders WHERE client_order_id = ?",
            (client_order_id,),
        ).fetchone()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "OrderStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()