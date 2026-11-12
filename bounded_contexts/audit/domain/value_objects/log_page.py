"""Page specification for log searches (``limit`` rows, newest first, starting at row ``offset``).

The upper limit is enforced here so oversized fetches do not clog the DB and the screen. A value
object so boundary decisions are not scattered across endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@dataclass(frozen=True)
class LogPage:
    """Range of one page. Always ``1 <= limit <= MAX_LIMIT`` and ``offset >= 0``."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}: {self.limit}")
        if self.offset < 0:
            raise ValueError(f"offset must be 0 or greater: {self.offset}")

    @classmethod
    def of(cls, limit: int | None = None, offset: int | None = None) -> LogPage:
        """Create it with unspecified or out-of-range values rounded to defaults (the entry for external input)."""
        clamped_limit = DEFAULT_LIMIT if limit is None or limit < 1 else min(limit, MAX_LIMIT)
        return cls(limit=clamped_limit, offset=max(offset or 0, 0))


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "LogPage"]
