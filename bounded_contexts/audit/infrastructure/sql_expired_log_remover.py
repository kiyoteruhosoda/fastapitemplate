"""Deletion of rows past their retention period (both ``log`` and ``audit_log``).

Writes over **a short-lived connection separate from any request session**. The caller is a
resident thread outside requests, so there is no existing session to ride on.

**Deletes in small batches by primary key rather than one big DELETE.** The first cleanup of
accumulated rows can target hundreds of thousands of rows. A single statement would hold those
rows in one long transaction on MariaDB, and hold the whole-DB write lock for that time on SQLite.
Both make requests wait, so each round is bounded with gaps in between.

``DELETE ... LIMIT`` depends on the backend (not available in the SQLite bundled with Python), so
it is done in two steps: "select the IDs to delete -> delete those IDs".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

import sqlalchemy as sa

from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from shared.infrastructure.models.log import Log
from shared.kernel.database.db import get_engine

DEFAULT_CHUNK_SIZE = 1000


class SqlExpiredLogRemover:
    """Delete rows older than *cutoff*, in small batches by primary key."""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    def delete_application_logs_before(self, cutoff: datetime) -> int:
        return _delete_in_chunks(
            sa.select(Log.id).where(Log.created_at < cutoff).order_by(Log.id),
            lambda ids: sa.delete(Log).where(Log.id.in_(ids)),
            self._chunk_size,
        )

    def delete_audit_logs_before(self, cutoff: datetime) -> int:
        return _delete_in_chunks(
            sa.select(AuditLogModel.id).where(AuditLogModel.occurred_at < cutoff).order_by(AuditLogModel.id),
            lambda ids: sa.delete(AuditLogModel).where(AuditLogModel.id.in_(ids)),
            self._chunk_size,
        )


def _delete_in_chunks(
    expired_ids: sa.Select[int],
    delete_by_ids: Callable[[Sequence[int]], sa.Delete],
    chunk_size: int,
) -> int:
    """Delete *chunk_size* rows at a time until none are left, and return the number of rows
    **actually deleted**.

    The transaction is closed after each chunk. If fewer than *chunk_size* rows were selected,
    that was the last chunk (finish without querying again).

    What is counted is the number of rows ``DELETE`` removed, not the number of IDs selected.
    Several workers running at once may select the same IDs (no mutual exclusion; ADR-0075 §3).
    Whoever deletes first is the actual deleter, and the later ``DELETE`` hits 0 rows. Counting
    selections would have both report "deleted" the same rows, inflating the counts in the
    operational log.

    Whether to continue is decided by **the number selected**. Deciding by the number deleted
    would wrongly stop with "nothing left" on a chunk another worker got to first.
    """
    limited = expired_ids.limit(chunk_size)
    deleted = 0
    while True:
        with get_engine().begin() as connection:
            ids = list(connection.scalars(limited))
            if ids:
                deleted += connection.execute(delete_by_ids(ids)).rowcount
        if len(ids) < chunk_size:
            return deleted


__all__ = ["DEFAULT_CHUNK_SIZE", "SqlExpiredLogRemover"]
