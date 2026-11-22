"""
Hash-chained audit log for Vesper.

Every decision the Agent makes — including refusals — is appended here.
Each entry is hashed together with the previous entry's hash, forming a
tamper-evident chain: changing any past entry invalidates every hash
after it, which ``verify()`` detects.

Design principles
-----------------
- Deterministic: no time, no randomness, no environment reads. Given the
  same sequence of append() calls, the hashes are identical.
- Append-only interface: ``append()`` is the only writer. ``entries()``
  returns a shallow copy so callers cannot replace entries wholesale.
- Tamper-evident, not tamper-proof: an attacker with write access to the
  process can still rewrite both entries and hashes consistently. The
  guarantee is that silent modification during normal operation is
  detectable on the next ``verify()``.

Chain structure
---------------
    genesis      = "0" * 64
    hash[i]      = sha256(hash[i-1] + canonical(entry[i]))
    head         = hash[last]  (or None if empty)

``canonical(entry)`` is ``json.dumps(entry, sort_keys=True,
separators=(",", ":"), ensure_ascii=False).encode("utf-8")`` — stable
across runs and Python versions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


_GENESIS = "0" * 64


def _canonical(entry: dict) -> bytes:
    """Stable byte representation of a log entry, used for hashing."""
    return json.dumps(
        entry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class MemoryLog:
    """Append-only hash-chained log held in memory."""

    def __init__(self) -> None:
        # Parallel arrays: _entries[i] is the payload, _hashes[i] is its
        # chain hash. Keeping them separate means a caller who mutates a
        # dict returned by entries() is detectable: the stored hash no
        # longer matches the payload on the next verify().
        self._entries: list[dict] = []
        self._hashes: list[str] = []

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
            raise TypeError(f"log entry must be a dict, got {type(entry).__name__}")

        prev = self._hashes[-1] if self._hashes else _GENESIS
        h = hashlib.sha256(prev.encode("ascii") + _canonical(entry)).hexdigest()
        self._entries.append(entry)
        self._hashes.append(h)
        return h

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._entries)

    @property
    def head(self) -> Optional[str]:
        """Hash of the most recent entry, or None if the log is empty."""
        return self._hashes[-1] if self._hashes else None

    def entries(self) -> list[dict]:
        """
        Return a shallow copy of the entry list, in append order.

        The list is a new object, so callers can iterate and slice without
        affecting the log. The dicts inside are the originals; mutating
        them is detected by ``verify()``.
        """
        return list(self._entries)

    # ------------------------------------------------------------------ #
    # Integrity
    # ------------------------------------------------------------------ #
    def verify(self) -> bool:
        """
        Return True iff the chain is intact: every hash matches its entry
        and links correctly to the previous hash.

        Returns False on the first mismatch. Does not raise on corrupt
        entries — a malformed entry just counts as a mismatch.
        """
        prev = _GENESIS
        for entry, stored in zip(self._entries, self._hashes):
            try:
                recomputed = hashlib.sha256(
                    prev.encode("ascii") + _canonical(entry)
                ).hexdigest()
            except (TypeError, ValueError):
                return False
            if recomputed != stored:
                return False
            prev = stored
        return True