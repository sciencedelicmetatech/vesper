"""
Hash-chained audit log for Vesper.

Every decision the Agent makes — including refusals — is appended here.
Each entry is hashed together with the previous entry's hash, forming a
tamper-evident chain: changing any past entry invalidates every hash
after it, which ``verify()`` detects.

Design principles
-----------------
- Deterministic: no time, no randomness, no environment reads. Given the
  same sequence of ``append()`` calls, the hashes are identical.
- Append-only interface: ``append()`` is the only writer. ``entries()``
  returns a shallow copy so callers cannot replace entries wholesale.
- Tamper-evident, not tamper-proof: an attacker with write access to the
  process can still rewrite both entries and hashes consistently. The
  guarantee is that silent modification during normal operation is
  detectable on the next ``verify()``.

Chain structure
---------------
    genesis      = "0" * 64
    hash[i]      = sha256(hash[i-1] + canonical(payload[i]))
    head         = hash[last]  (or None if empty)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional


_GENESIS = "0" * 64


def _canonical(payload: dict) -> bytes:
    """Stable byte representation of an entry payload, used for hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass
class _Entry:
    payload: dict
    hash: str


class MemoryLog:
    """Append-only hash-chained log held in memory."""

    def __init__(self) -> None:
        self._entries: list[_Entry] = []

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def append(self, entry: dict) -> str:
        """
        Append an entry and return its chain hash.

        The entry is stored as-is (not copied). Callers must not mutate it
        afterwards; doing so is detected by ``verify()``.
        """
        if not isinstance(entry, dict):
            raise TypeError(
                f"log entry must be a dict, got {type(entry).__name__}"
            )

        prev = self._entries[-1].hash if self._entries else _GENESIS
        h = hashlib.sha256(
            prev.encode("ascii") + _canonical(entry)
        ).hexdigest()
        self._entries.append(_Entry(payload=entry, hash=h))
        return h

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._entries)

    @property
    def head(self) -> Optional[str]:
        """Hash of the most recent entry, or None if the log is empty."""
        return self._entries[-1].hash if self._entries else None

    def entries(self) -> list[dict]:
        """
        Return a shallow copy of the entry payloads in append order.

        Used by tests and by the paper-trade harness to snapshot the log
        without exposing mutation access to the internal list. Returns a
        new list on every call; the dicts inside are the originals.
        """
        return [e.payload for e in self._entries]

    # ------------------------------------------------------------------ #
    # Integrity
    # ------------------------------------------------------------------ #
    def verify(self) -> bool:
        """
        Return True iff the chain is intact: every hash matches its entry
        payload and links correctly to the previous hash.

        Returns False on the first mismatch. Does not raise on corrupt
        entries — a malformed payload just counts as a mismatch.
        """
        prev = _GENESIS
        for e in self._entries:
            try:
                recomputed = hashlib.sha256(
                    prev.encode("ascii") + _canonical(e.payload)
                ).hexdigest()
            except (TypeError, ValueError):
                return False
            if recomputed != e.hash:
                return False
            prev = e.hash
        return True