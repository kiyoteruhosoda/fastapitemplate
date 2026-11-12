"""Queue of log rows emitted during a request (waiting to be written to the ``log`` table).

``DbLogHandler`` INSERTs each row over a dedicated connection. Doing that mid-request **collides
with the write lock held by the request's session** (SQLite). With the default
``sqlite:///app.db`` it fails after waiting the busy timeout (5 seconds), and since the handler
swallows the exception, "one log line takes 5 seconds and is not even stored in the DB".

So rows are collected here mid-request and written together after the request has been processed
(the same construction as audit logs; ADR-0075 §1). Outside the middleware (startup, scripts)
nobody holds the lock, so rows are written on the spot.
"""

from __future__ import annotations

from contextvars import ContextVar

# One row to write (column name -> value). Built by the handler; the batch writer INSERTs it as is.
LogRow = dict[str, object]


class PendingLogRecords:
    """Queue for one request."""

    def __init__(self) -> None:
        self._rows: list[LogRow] = []

    def add(self, row: LogRow) -> None:
        self._rows.append(row)

    def drain(self) -> tuple[LogRow, ...]:
        """Take the queued rows and empty the queue (prevents double writes)."""
        rows = tuple(self._rows)
        self._rows.clear()
        return rows


_pending_records_var: ContextVar[PendingLogRecords | None] = ContextVar("pending_log_records", default=None)


def install_pending_log_records() -> PendingLogRecords:
    """Prepare and return this request's queue (called first by the middleware)."""
    pending = PendingLogRecords()
    _pending_records_var.set(pending)
    return pending


def current_pending_log_records() -> PendingLogRecords | None:
    """Queue of the request in progress. ``None`` outside a request (write on the spot)."""
    return _pending_records_var.get()


__all__ = [
    "LogRow",
    "PendingLogRecords",
    "current_pending_log_records",
    "install_pending_log_records",
]
