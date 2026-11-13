"""Interfaces for collecting and writing audit events (implemented in outer layers).

Collecting and writing are separate. **Collecting involves no I/O and cannot fail** (it is called
mid-processing), whereas **writing does I/O and can fail** (done once after the request has been
processed). Their responsibilities differ, so they are not merged into one interface.

The other reason for the split is SQLite (used as the development/test DB per ADR-0071 §1).
Writing from another connection mid-processing collides with the write lock held by the
request's session and gives `database is locked`. Moving writes outside the request removes the
lock contention altogether (ADR-0075 §1).

Reading is :mod:`~bounded_contexts.audit.domain.repositories.audit_log_query`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent


class AuditEventCollector(Protocol):
    """Where audit events raised mid-processing are queued."""

    def add(self, event: AuditEvent) -> None:
        """Queue *event*. Does no I/O, so it cannot fail."""


class AuditEventRecorder(Protocol):
    """Where queued audit events are persisted."""

    def record_all(self, events: Sequence[AuditEvent]) -> None:
        """Write *events* in order of occurrence in one transaction.

        The caller's processing (the request) has already finished. Events of requests that were
        rolled back, such as failed sign-in attempts, are written here too.
        """


__all__ = ["AuditEventCollector", "AuditEventRecorder"]
