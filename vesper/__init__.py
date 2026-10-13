"""Vesper - deterministic, refusal-first trading agent."""

from vesper.state import MarketState
from vesper.log import MemoryLog, LogEntry
from vesper.posterior import BetaPosterior
from vesper.decider import (
    Decider,
    DeciderConfig,
    Signal,
    Refusal,
    Side,
    Decision,
)
from vesper.agent import Agent

__version__ = "1.0.0"
__all__ = [
    "MarketState",
    "MemoryLog",
    "LogEntry",
    "BetaPosterior",
    "Decider",
    "DeciderConfig",
    "Signal",
    "Refusal",
    "Side",
    "Decision",
    "Agent",
]