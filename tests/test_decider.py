from vesper.decider import Decider, DeciderConfig, Refusal, Signal
from vesper.state import MarketState


def _tick(mom: float = 0.0, spread_bps: float = 2.0, vol: int = 1000) -> MarketState:
    mid = 100.0
    spread = mid * spread_bps / 10000.0
    return MarketState(
        "T", 0, mid - spread / 2, mid + spread / 2, mid, vol, (mom,)
    )


def test_spread_gate():
    d = Decider(DeciderConfig(explore_ticks=0))
    assert isinstance(d.decide(_tick(spread_bps=100.0)), Refusal)


def test_volume_gate():
    d = Decider(DeciderConfig(explore_ticks=0, min_volume=1000))
    assert isinstance(d.decide(_tick(vol=1)), Refusal)


def test_exploration_trades():
    d = Decider(DeciderConfig(explore_ticks=10))
    r = d.decide(_tick(mom=0.5))
    assert isinstance(r, Signal)
    assert r.reason == "explore"


def test_zero_momentum_refuses():
    d = Decider(DeciderConfig(explore_ticks=0))
    assert isinstance(d.decide(_tick(mom=0.0)), Refusal)


def test_low_volume_crypto_tick():
    """Crypto bars often have volume of 1. Volume gate must not refuse them."""
    d = Decider(DeciderConfig(explore_ticks=10, min_volume=1))
    r = d.decide(_tick(mom=0.5, vol=1))
    # Volume gate accepted the tick; exploration phase fires.
    assert isinstance(r, Signal)
    assert r.reason == "explore"


def test_buy_on_positive_momentum():
    d = Decider(DeciderConfig(explore_ticks=10))
    r = d.decide(_tick(mom=0.5))
    assert isinstance(r, Signal)
    assert r.side.value == "BUY"


def test_sell_on_negative_momentum():
    d = Decider(DeciderConfig(explore_ticks=10))
    r = d.decide(_tick(mom=-0.5))
    assert isinstance(r, Signal)
    assert r.side.value == "SELL"