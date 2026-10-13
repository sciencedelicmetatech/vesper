from vesper.cli import walk_forward
from vesper.data import make_ticks_realistic
from vesper.decider import DeciderConfig


def test_same_seed_same_head():
    cfg = DeciderConfig()
    ticks = make_ticks_realistic(500, seed=42, edge=0.3)
    r1 = walk_forward(ticks, cfg)
    r2 = walk_forward(ticks, cfg)
    assert r1["online_agent"].log.head == r2["online_agent"].log.head


def test_chain_valid_after_walkforward():
    cfg = DeciderConfig()
    ticks = make_ticks_realistic(500, seed=0, edge=0.3)
    r = walk_forward(ticks, cfg)
    assert r["train_agent"].log.verify()
    assert r["frozen_agent"].log.verify()
    assert r["online_agent"].log.verify()