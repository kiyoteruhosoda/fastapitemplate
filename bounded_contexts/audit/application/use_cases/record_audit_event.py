"""Use case that builds an audit event and queues it.

Callers (routers) do not build the request context each time; they receive this use case, bound
per request, via ``Depends()``. ``execute`` is given only "what was done and how it turned out".

**It does not write to the DB.** It only queues; the actual write is done in one go by
:class:`~bounded_contexts.audit.application.use_cases.write_audit_events.WriteAuditEvents`
after the request has been processed (ADR-0075 §1). Writing from another connection mid-request
would collide on SQLite with the write lock held by the request's session.
"""

from __future__ import annotations

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.repositories.audit_event_recorder import (
    AuditEventCollector,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget
from shared.kernel.timestamps import utcnow


class RecordAuditEvent:
    """Holds the context of one request and builds the audit events during that request."""

    def __init__(
        self,
        collector: AuditEventCollector,
        context: AuditRequestContext,
        actor_user_id: int | None = None,
    ) -> None:
        self._collector = collector
        self._context = context
        self._actor_user_id = actor_user_id

    def as_actor(self, actor_user_id: int) -> RecordAuditEvent:
        """Return a recorder with the actor replaced.

        The actor is normally fixed at the start of the request (authentication dependency), but
        **only sign-in fixes it midway**, so it is rebound at that point. Allowing an actor per call
        would make it easy to pass the other party as the actor for unauthenticated operations
        (exactly the misattribution fixed in ADR-0075 §1).
        """
        return RecordAuditEvent(self._collector, self._context, actor_user_id)

    def execute(
        self,
        event_type: AuditEventType,
        result: AuditResult = AuditResult.SUCCESS,
        *,
        target: AuditTarget | None = None,
        reason: str | None = None,
    ) -> None:
        """Record one event (written after the request ends).

        The actor is the **authenticated user** bound to this recorder, and stays ``None`` for
        unauthenticated requests. When "who did it is unknown but whom it was done to is known"
        (sign-in failure, password reset), put the other party in ``target``.

        ``reason`` holds the failure reason or the names of changed items. **Never pass the values
        themselves (passwords, email addresses, etc.).**
        """
        self._collector.add(
            AuditEvent(
                event_type=event_type,
                result=result,
                occurred_at=utcnow(),
                context=self._context,
                actor_user_id=self._actor_user_id,
                target=target,
                reason=reason,
            )
        )


__all__ = ["RecordAuditEvent"]
