#!/usr/bin/env python3
"""Frozen vs online walk-forward across edge strengths."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vesper.cli import _phase, multi_seed
from vesper.data import make_ticks_realistic
from vesper.decider import DeciderConfig

cfg = DeciderConfig()
for edge in (0.0, 0.2, 0.3, 0.4):
    print(f"edge={edge}")
    r = multi_seed(make_ticks_realistic, 10, 2000, cfg, edge=edge)
    _phase("train", r["train"])
    _phase("test frozen", r["test_frozen"])
    _phase("test online", r["test_online"])