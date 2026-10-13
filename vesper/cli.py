"""Command-line entry point."""

from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Any, Callable, Dict, List

from vesper import __version__
from vesper.agent import Agent
from vesper.data import acquire, make_ticks_realistic
from vesper.decider import DeciderConfig
from vesper.state import MarketState


def _metrics(agent: Agent, cfg: DeciderConfig) -> Dict[str, Any]:
    wins = losses = 0
    gross = 0.0
    for e in agent.log._entries:
        p = e.payload
        if p.get("type") == "RESOLVE":
            sz = p.get("size", 1.0)
            if p["win"]:
                wins += 1
                gross += sz
            else:
                losses += 1
                gross -= sz
    trades = wins + losses
    cpt = cfg.cost_bps / (cfg.stop_pct * 10000.0)
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "gross_r": gross,
        "net_r": gross - trades * cpt,
        "win_rate": (wins / trades) if trades else 0.0,
        "posterior_n": agent.decider.posterior.n,
        "posterior_mean": round(agent.decider.posterior.mean, 4),
        "chain_valid": agent.log.verify(),
    }


def walk_forward(
    ticks: List[MarketState], cfg: DeciderConfig, train_frac: float = 0.7
) -> Dict[str, Any]:
    split = int(len(ticks) * train_frac)
    tr, te = ticks[:split], ticks[split:]

    train = Agent(cfg, frozen=False)
    for t in tr:
        train.on_tick(t)

    frozen = Agent(cfg, frozen=True)
    frozen.decider.posterior = train.decider.posterior.clone()
    frozen.decider._tick_index = cfg.explore_ticks
    for t in te:
        frozen.on_tick(t)

    online = Agent(cfg, frozen=False)
    online.decider.posterior = train.decider.posterior.clone()
    online.decider._tick_index = cfg.explore_ticks
    for t in te:
        online.on_tick(t)

    return {
        "train": _metrics(train, cfg),
        "test_frozen": _metrics(frozen, cfg),
        "test_online": _metrics(online, cfg),
        "train_agent": train,
        "frozen_agent": frozen,
        "online_agent": online,
    }


def multi_seed(
    fn: Callable[..., List[MarketState]],
    n_seeds: int,
    n_ticks: int,
    cfg: DeciderConfig,
    train_frac: float = 0.7,
    **kwargs: Any,
) -> Dict[str, Any]:
    keys = ["trades", "win_rate", "net_r"]
    agg: Dict[str, Dict[str, List[float]]] = {
        p: {k: [] for k in keys} for p in ("train", "test_frozen", "test_online")
    }
    for s in range(n_seeds):
        r = walk_forward(fn(n_ticks, seed=s, **kwargs), cfg, train_frac)
        for p in agg:
            for k in keys:
                agg[p][k].append(r[p][k])
    out: Dict[str, Any] = {}
    for p in agg:
        out[p] = {
            k: {
                "mean": statistics.fmean(v),
                "std": statistics.pstdev(v) if len(v) > 1 else 0.0,
                "values": v,
            }
            for k, v in agg[p].items()
        }
    return out


def _phase(name: str, m: Dict[str, Any]) -> None:
    print(
        f"  {name:<16} | trades {m['trades']['mean']:7.1f}"
        f" +/- {m['trades']['std']:6.1f}"
        f" | wr {m['win_rate']['mean']:7.4f}"
        f" | net_r {m['net_r']['mean']:8.2f}"
        f" +/- {m['net_r']['std']:7.2f}"
    )


def main() -> None:
    SEEDS, N = 10, 2000
    cfg = DeciderConfig()
    print(f"Vesper v{__version__}")
    print("=" * 78)

    source, real = acquire()
    print(f"[0] Source: {source} ({len(real) if real else 0} ticks)")

    if real:
        print("\n[0b] Walk-forward on real data")
        print("  phase            | trades | win_rate | net_r")
        r = walk_forward(real, cfg)
        for p in ("train", "test_frozen", "test_online"):
            m = r[p]
            print(
                f"  {p:<16} | {m['trades']:6d} | {m['win_rate']:8.4f}"
                f" | {m['net_r']:7.2f}"
            )

    print("\n[1] Ablation (synthetic, edge=0.3)")
    r = multi_seed(make_ticks_realistic, SEEDS, N, cfg, edge=0.3)
    _phase("train", r["train"])
    _phase("test frozen", r["test_frozen"])
    _phase("test online", r["test_online"])

    print("\n[3] Boundary regime (synthetic, edge=0.2)")
    r = multi_seed(make_ticks_realistic, SEEDS, N, cfg, edge=0.2)
    _phase("train", r["train"])
    _phase("test frozen", r["test_frozen"])
    _phase("test online", r["test_online"])
    delta = r["test_online"]["net_r"]["mean"] - r["test_frozen"]["net_r"]["mean"]
    print(f"  delta: {'+' if delta >= 0 else ''}{delta:.2f}")

    print("\n[4] Cost break-even sweep (edge=0.3, stop=0.5%)")
    print("  cost_bps | net_r (mean+/-std) | verdict")
    for c in (0.0, 1.0, 2.0, 5.0, 7.0, 10.0, 20.0):
        cfg_c = replace(cfg, cost_bps=c)
        r = multi_seed(make_ticks_realistic, SEEDS, N, cfg_c, edge=0.3)
        mean = r["test_frozen"]["net_r"]["mean"]
        std = r["test_frozen"]["net_r"]["std"]
        verdict = "PROFIT" if mean > 0 else "DEAD"
        print(f"  {c:<9}| {mean:8.2f} +/- {std:6.2f} | {verdict}")


if __name__ == "__main__":
    main()