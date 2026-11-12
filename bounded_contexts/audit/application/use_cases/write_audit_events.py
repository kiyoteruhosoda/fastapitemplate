"""Use case that persists queued audit events.

Called exactly once after the request's processing (DB session commit / rollback) has fully
finished. By then the request's transaction is closed, so even on SQLite there is no write lock
contention (ADR-0075 §1).

A write failure does not bring down the caller. Even when audit logs cannot be written (before
migrations, DB failure), a response already returned cannot be undone, so the failure is written
to the application log and processing continues.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent
from bounded_contexts.audit.domain.repositories.audit_event_recorder import (
    AuditEventRecorder,
)

logger = logging.getLogger(__name__)


class WriteAuditEvents:
    def __init__(self, recorder: AuditEventRecorder) -> None:
        self._recorder = recorder

    def execute(self, events: Sequence[AuditEvent]) -> None:
        if not events:
            return
        try:
            self._recorder.record_all(events)
        except Exception:
            logger.exception(
                "Failed to record audit events",
                extra={"audit_event_count": len(events)},
            )


__all__ = ["WriteAuditEvents"]
