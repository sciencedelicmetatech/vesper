def reconcile(agent, broker, store, logger):
    """On startup: resolve any orders that were in-flight at crash time."""
    for (coid,) in store.unresolved():
        f = broker.get_order_by_client_id(coid)
        if f is None:
            logger.warning("order %s missing at broker — assuming rejected", coid)
            store.save(coid, "", "", "", 0, "rejected", None)
            continue
        store.save(coid, f.order_id, f.symbol, f.side, f.filled_qty,
                   f.status, f.filled_avg_price)
        if f.status == "filled":
            logger.info("reconciled %s @ %s", coid, f.filled_avg_price)