"""Append-only hash-chained decision log."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class LogEntry:
    index: int
    prev_hash: str
    payload: Dict[str, Any]
    entry_hash: str = ""

    def compute_hash(self) -> str:
        blob = json.dumps(
            {
                "index": self.index,
                "prev_hash": self.prev_hash,
                "payload": self.payload,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()


class MemoryLog:
    """Append-only list of entries. Any rewrite breaks the chain."""

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._entries: List[LogEntry] = []

    def append(self, payload: Dict[str, Any]) -> LogEntry:
        prev = self._entries[-1].entry_hash if self._entries else self.GENESIS
        e = LogEntry(index=len(self._entries), prev_hash=prev, payload=payload)
        e.entry_hash = e.compute_hash()
        self._entries.append(e)
        return e

    def verify(self) -> bool:
        prev = self.GENESIS
        for e in self._entries:
            if e.prev_hash != prev or e.entry_hash != e.compute_hash():
                return False
            prev = e.entry_hash
        return True

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def head(self) -> Optional[str]:
        return self._entries[-1].entry_hash if self._entries else None