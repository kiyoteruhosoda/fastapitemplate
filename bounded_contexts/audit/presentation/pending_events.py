"""Queue of audit events raised during a request.

Audit events are raised mid-processing, but **written after the request has been processed**
(ADR-0075 §1). Until then, events accumulate here.

The queue travels in ``contextvars``. Logging and auditing are cross-cutting concerns, and passing
them through every function would bury their actual responsibilities (same reason as
:mod:`shared.kernel.logging.request_context`).

The middleware **creates the queue object first** and then calls downstream, with both sides using
the same object. Handing it over by sharing a mutable object rather than relying on the result of
``ContextVar.set()`` means nothing is lost even when downstream runs in another task (e.g. with
``BaseHTTPMiddleware`` in between).
"""

from __future__ import annotations

from contextvars import ContextVar

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent


class PendingAuditEvents:
    """Queue for one request (implementation of the Domain ``AuditEventCollector``).

    It does no I/O, so it cannot fail. The split also ensures auditing never raises exceptions
    mid-processing (write failures are handled by ``WriteAuditEvents``).
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self._events.append(event)

    def drain(self) -> tuple[AuditEvent, ...]:
        """Take the queued events and empty the queue (prevents double writes)."""
        events = tuple(self._events)
        self._events.clear()
        return events


_pending_events_var: ContextVar[PendingAuditEvents | None] = ContextVar("pending_audit_events", default=None)


def install_pending_events() -> PendingAuditEvents:
    """Prepare and return this request's queue (called first by the middleware)."""
    pending = PendingAuditEvents()
    _pending_events_var.set(pending)
    return pending


def current_pending_events() -> PendingAuditEvents | None:
    """Queue of the request in progress. ``None`` outside the middleware (scripts etc.)."""
    return _pending_events_var.get()


__all__ = ["PendingAuditEvents", "current_pending_events", "install_pending_events"]
