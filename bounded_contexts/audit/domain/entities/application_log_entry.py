"""Read model of application logs (one row of the ``log`` table).

Writing is done by ``DbLogHandler`` in :mod:`shared.kernel.logging` (logging is a concern across
all layers, so the writing side does not belong to the audit context). This is the type for **the
side that reads the table for viewing**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ApplicationLogEntry:
    """One row of ``log``. Contains no PII (users appear only as ``user_id_hash``)."""

    id: int
    created_at: datetime
    level: str
    logger: str
    message: str
    request_id: str | None = None
    user_id_hash: str | None = None
    path: str | None = None
    method: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    trace: str | None = None


@dataclass(frozen=True)
class ApplicationLogPage:
    """One page of search results and the total count matching the criteria."""

    entries: tuple[ApplicationLogEntry, ...] = field(default_factory=tuple)
    total: int = 0


__all__ = ["ApplicationLogEntry", "ApplicationLogPage"]
