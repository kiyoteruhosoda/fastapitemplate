"""``Depends()`` dependencies of the audit context.

The concrete classes (SQLAlchemy implementations) are assembled only here, and routers receive use
cases. The request context (``requestId``, client address, acting principal) is taken from
:mod:`shared.kernel.logging.request_context`, so routers that record audits do not receive
tracking information as arguments.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.application.use_cases.search_application_logs import (
    SearchApplicationLogs,
)
from bounded_contexts.audit.application.use_cases.search_audit_logs import (
    SearchAuditLogs,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.infrastructure.sql_application_log_repository import (
    SqlApplicationLogQuery,
)
from bounded_contexts.audit.infrastructure.sql_audit_log_repository import (
    SqlAuditLogQuery,
)
from bounded_contexts.audit.presentation.pending_events import (
    PendingAuditEvents,
    current_pending_events,
)
from presentation.fastapi.dependencies.auth import get_current_principal
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.logging.request_context import (
    current_actor_user_id,
    current_ip_address,
    current_request_id,
    current_user_agent,
)

logger = logging.getLogger(__name__)


def current_audit_context() -> AuditRequestContext:
    """Bundle the tracking information of the request in progress into a value object."""
    return AuditRequestContext(
        request_id=current_request_id(),
        ip_address=current_ip_address(),
        user_agent=current_user_agent(),
    )


def record_audit_event() -> RecordAuditEvent:
    """Audit event recorder for this request.

    Events go to the request's queue. The actual write is done after processing by
    :class:`~bounded_contexts.audit.presentation.middleware.AuditRecordingMiddleware`
    (ADR-0075 §1). That is why it does not take a DB session.

    When there is no queue (the middleware is missing), it hands out a discarding sink, lets the
    work proceed, and leaves a warning. Auditing silently stopping is worse than features failing
    because nothing can be recorded -- but being unable to notice that it silently stopped is
    worse still.
    """
    pending = current_pending_events()
    if pending is None:
        logger.warning("audit_recording_middleware_missing")
        pending = PendingAuditEvents()
    return RecordAuditEvent(
        collector=pending,
        context=current_audit_context(),
        actor_user_id=current_actor_user_id(),
    )


def search_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> SearchAuditLogs:
    # Only one's own tenant's records are readable (ADR-0079 §1). The filter is applied at the repository entry
    return SearchAuditLogs(SqlAuditLogQuery(db, principal.tenant_id))


def search_application_logs(db: Annotated[Session, Depends(get_db)]) -> SearchApplicationLogs:
    return SearchApplicationLogs(SqlApplicationLogQuery(db))


# Common type annotation used by routers that record audits
AuditRecorderDep = Annotated[RecordAuditEvent, Depends(record_audit_event)]

__all__ = [
    "AuditRecorderDep",
    "current_audit_context",
    "record_audit_event",
    "search_application_logs",
    "search_audit_logs",
]
