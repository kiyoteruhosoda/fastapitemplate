"""Record making each received DPoP proof single-use per key (ADR-0103. Implemented in Infrastructure)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class DpopProofReplayRepository(Protocol):
    def record_if_unused(self, replay_key: str, retain_until: datetime) -> bool:
        """If unused, record it and return ``True``; if already recorded, ``False`` (= reuse).

        ⚠ Don't do check-then-write in two steps (two concurrent requests would both pass).
        Decide with one insert into a unique key.
        Expired records are cleaned up at this opportunity. ``retain_until`` is tz-aware UTC.
        """
        ...


__all__ = ["DpopProofReplayRepository"]
