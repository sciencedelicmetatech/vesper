#!/usr/bin/env python3
"""Cost break-even sweep."""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vesper.cli import multi_seed
from vesper.data import make_ticks_realistic
from vesper.decider import DeciderConfig

cfg = DeciderConfig()
print("cost_bps | cost_R | net_r (mean+/-std) | verdict")
for c in (0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0):
    r = multi_seed(make_ticks_realistic, 10, 2000, replace(cfg, cost_bps=c), edge=0.3)
    m = r["test_frozen"]["net_r"]
    verdict = "PROFIT" if m["mean"] > 0 else "DEAD"
    print(
        f"{c:<9}| {c / (cfg.stop_pct * 10000):<7.3f}|"
        f" {m['mean']:8.2f} +/- {m['std']:6.2f} | {verdict}"
    )