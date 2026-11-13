"""Middleware that writes audit events.

Writes the events queued during a request together, **after the request has been fully processed**.

There are two reasons to write at this point (ADR-0075 §1).

1. **To keep failed sign-ins.** Writing through the request's session would lose the very event
   we most want to record when the 401 rolls back.
2. **To avoid write lock contention on SQLite.** Writing from another connection mid-request
   collides with the write lock held by the request's session and gives
   ``database is locked`` (it always happens with the default ``sqlite:///app.db``).

**It is written as a plain ASGI middleware** (not ``BaseHTTPMiddleware``).
FastAPI closes dependencies that use ``yield`` (the commit in ``get_db``) **after** sending the
response, but ``BaseHTTPMiddleware``'s ``call_next`` returns as soon as the start of the response
arrives. It would then write before the commit, causing the contention in 2 above.
``await self.app(...)`` waits for the downstream to finish, so it runs after the session is closed.

It also writes when exiting with an exception. Each queued event carries its own outcome
(``result``), and the request failing is a separate matter from whether to record.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from bounded_contexts.audit.application.use_cases.write_audit_events import (
    WriteAuditEvents,
)
from bounded_contexts.audit.infrastructure.sql_audit_log_repository import (
    SqlAuditEventRecorder,
)
from bounded_contexts.audit.presentation.pending_events import install_pending_events


class AuditRecordingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        pending = install_pending_events()
        try:
            await self.app(scope, receive, send)
        finally:
            WriteAuditEvents(SqlAuditEventRecorder()).execute(pending.drain())


__all__ = ["AuditRecordingMiddleware"]
