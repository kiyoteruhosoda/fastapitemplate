"""Handling of time.

Times that are stored or compared are always UTC and written to the DB as naive datetimes
(see "Logging" in CLAUDE.md). Mixing values with and without tz info makes comparisons raise,
so the producers and converters are gathered in this one place.

Converting displayed times to local time is the frontend's job; the server returns UTC as is.
But **strings leaving the API always carry ``Z``** (``isoformat_utc``). JavaScript's
``new Date()`` interprets an ISO string without an offset as local time, so forgetting it shifts
the screen by 9 hours.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a naive UTC datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_aware() -> datetime:
    """Return the current time as tz-aware UTC (for values handled with tz, such as JWT times or
    the ``/healthz`` display)."""
    return datetime.now(UTC)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize an externally received datetime to naive UTC comparable with stored values.

    A tz-aware input such as ``2026-07-30T09:00:00+09:00`` is converted to UTC and then its tz is
    dropped. An input without tz is taken to be UTC already (stored values are naive UTC).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def isoformat_utc(value: datetime) -> str:
    """ISO string for leaving the API. Always ends with ``Z``.

    Naive values are taken to be UTC (stored values are naive UTC). Browsers read an ISO string
    without ``Z`` as local time, so every value crossing the boundary must go through here.
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


__all__ = ["isoformat_utc", "to_naive_utc", "utcnow", "utcnow_aware"]
