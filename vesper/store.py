import json, sqlite3, time
from pathlib import Path

class OrderStore:
    def __init__(self, path: str = "vesper_orders.db"):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS orders (
            client_order_id TEXT PRIMARY KEY,
            order_id TEXT, symbol TEXT, side TEXT, qty REAL,
            status TEXT, filled_avg_price REAL, created_at REAL
        )""")
        self.db.commit()

    def save(self, coid, oid, symbol, side, qty, status, fill_price):
        self.db.execute(
            "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?)",
            (coid, oid, symbol, side, qty, status, fill_price, time.time()))
        self.db.commit()

    def unresolved(self):
        return self.db.execute(
            "SELECT client_order_id FROM orders WHERE status IN ('new','partially_filled','accepted')"
        ).fetchall()