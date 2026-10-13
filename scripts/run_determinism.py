#!/usr/bin/env python3
"""Determinism + tamper check. Exits 1 on failure."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vesper.cli import walk_forward
from vesper.data import make_ticks_realistic
from vesper.decider import DeciderConfig

cfg = DeciderConfig()
ticks = make_ticks_realistic(2000, seed=42, edge=0.3)
r1 = walk_forward(ticks, cfg)
r2 = walk_forward(ticks, cfg)

h1 = r1["online_agent"].audit()["head"]
h2 = r2["online_agent"].audit()["head"]

print(f"run 1 head: {h1}")
print(f"run 2 head: {h2}")
print(f"identical : {h1 == h2}")

r1["online_agent"].log._entries[1].payload["decision"] = {"type": "TAMPER"}
tamper_ok = not r1["online_agent"].log.verify()
print(f"tampered  : {tamper_ok} (should be True)")

if h1 != h2 or not tamper_ok:
    sys.exit(1)
print("PASS")