from vesper.brokers.alpaca import Fill
from vesper.brokers.mock import MockBroker
from vesper.store import OrderStore
from vesper.reconcile import reconcile


def test_unknown_order_marked_rejected():
    store = OrderStore(path=":memory:")
    store.save("ghost", "", "XBTUSD", "buy", 0.01, "new", None)
    broker = MockBroker()          # knows nothing
    stats = reconcile(broker, store, logger=lambda _: None)
    assert stats == {"checked": 1, "resolved": 0, "rejected": 1}
    assert store.get("ghost")["status"] == "rejected"


def test_known_order_overwritten_from_broker():
    store = OrderStore(path=":memory:")
    store.save("abc", "o1", "XBTUSD", "buy", 0.01, "new", None)
    broker = MockBroker(scripted_fills=[Fill(
        order_id="o1", client_order_id="abc", status="filled",
        filled_qty=0.01, filled_avg_price=31_000.0,
        symbol="XBTUSD", side="buy",
    )])
    # Seed the broker's idempotency map so get_order_by_client_id finds it
    broker.submit_market_order("XBTUSD", 0.01, "buy", client_order_id="abc")
    stats = reconcile(broker, store, logger=lambda _: None)
    assert stats == {"checked": 1, "resolved": 1, "rejected": 0}
    row = store.get("abc")
    assert row["status"] == "filled"
    assert row["filled_avg_price"] == 31_000.0