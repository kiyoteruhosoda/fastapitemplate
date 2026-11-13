"""Handler that writes to the ``log`` table.

- ``requestId`` is taken from the record (set by ``RequestContextFilter``).
- When the DB is not reachable, before migrations, or on write failure, it silently gives up
  (the actual work is never brought down for the sake of logging).
- SQLAlchemy's own logs are excluded because writing them would recurse.
- Records below ``LOG_DB_MIN_LEVEL`` are not written. The structured stdout log keeps everything
  at ``LOG_LEVEL``, while only the DB growth can be curbed separately
  (default ``INFO``; if log volume becomes a problem, raise it to ``WARNING`` on the admin screen).
- **During a request, rows are only queued**; the actual INSERT is done in one go by
  :class:`~presentation.fastapi.middleware.deferred_log_writes.DeferredLogWriteMiddleware`
  after the request has been processed. Writing from another connection mid-request would
  collide with the write lock held by the request's session
  (:mod:`shared.kernel.logging.pending_records`).
"""

from __future__ import annotations

import logging
import traceback as tb_module
from collections.abc import Sequence

import sqlalchemy as sa

from shared.kernel.logging.pending_records import (
    LogRow,
    current_pending_log_records,
)

_EXCLUDED_LOGGER_PREFIXES = ("sqlalchemy", "alembic", "shared.kernel.logging")

# Level name -> number. So that an unknown configured name does not stop writing, everything
# passes (equivalent to DEBUG) when it cannot be resolved.
_LEVEL_NUMBERS = logging.getLevelNamesMapping()


def _threshold(level_name: str) -> int:
    return _LEVEL_NUMBERS.get(level_name.strip().upper(), logging.DEBUG)


def write_log_rows(rows: Sequence[LogRow]) -> None:
    """Write the queued rows in one transaction.

    Called after the request has been processed (by the middleware). Exceptions propagate as is
    (whether to swallow them is the caller's decision).
    """
    if not rows:
        return
    from shared.infrastructure.models.log import Log
    from shared.kernel.database.db import get_engine

    with get_engine().begin() as connection:
        connection.execute(sa.insert(Log), list(rows))


class DbLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_EXCLUDED_LOGGER_PREFIXES):
            return
        try:
            from shared.kernel.settings.settings import settings

            if not settings.log_to_database:
                return
            if record.levelno < _threshold(settings.log_db_min_level):
                return

            row = _to_row(record)
            pending = current_pending_log_records()
            if pending is None:
                # Outside a request (startup, scripts). Nothing to collide with
                write_log_rows([row])
            else:
                pending.add(row)
        except Exception:
            # Never bring down the actual work for logging. But **do not stay silent**: making this
            # ``pass`` leaves "no logs on the admin screen" as the only symptom, with the cause
            # (DB not reachable, before migrations, column mismatch) invisible to everyone.
            # ``handleError`` only prints the traceback to stderr and does not re-enter logging
            # (no path that tries to write to the DB and fails again).
            self.handleError(record)


def _to_row(record: logging.LogRecord) -> LogRow:
    from shared.infrastructure.models.base import utcnow

    trace = None
    if record.exc_info and record.exc_info[0] is not None:
        trace = "".join(tb_module.format_exception(*record.exc_info))

    # The duration_ms column is Integer. SQLite's type affinity would keep a float as is, so round
    # before writing to make both backends behave the same.
    duration_ms = getattr(record, "duration_ms", None)
    if duration_ms is not None:
        duration_ms = round(float(duration_ms))

    return {
        "created_at": utcnow(),
        "level": record.levelname,
        "logger": record.name[:120],
        "message": record.getMessage(),
        "request_id": getattr(record, "request_id", None),
        "user_id_hash": getattr(record, "user_id_hash", None),
        "path": getattr(record, "path", None),
        "method": getattr(record, "method", None),
        "status_code": getattr(record, "status_code", None),
        "duration_ms": duration_ms,
        "trace": trace,
    }


__all__ = ["DbLogHandler", "write_log_rows"]
