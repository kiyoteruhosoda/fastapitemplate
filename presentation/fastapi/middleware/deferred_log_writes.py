"""Middleware that batch-writes app logs (the ``log`` table).

Log rows emitted during a request are written at once **after the request has fully finished**.
An INSERT from another connection mid-request collides with the write lock held by the request's
session, and on SQLite the row is lost after the busy timeout (5 s)
(:mod:`shared.kernel.logging.pending_records`).

**Written as a plain ASGI middleware** (not ``BaseHTTPMiddleware``). FastAPI closes ``yield``
dependencies (``get_db``'s commit) **after** sending the response, so the session is still open
when ``call_next`` returns. ``await self.app(...)`` waits for the downstream to finish, so this
reliably runs after commit / rollback.

Audit logs have the same mechanism, but the writes have a different owner, so they are separate
(app logs belong to the logging infrastructure, audit logs to the audit context; ADR-0075 §1).
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from shared.kernel.logging.db_log_handler import write_log_rows
from shared.kernel.logging.pending_records import install_pending_log_records

# This logger is excluded by DbLogHandler (it lives under ``shared.kernel.logging``),
# so a log about a failed write does not trigger another write.
logger = logging.getLogger("shared.kernel.logging.deferred_writes")


class DeferredLogWriteMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        pending = install_pending_log_records()
        try:
            await self.app(scope, receive, send)
        finally:
            try:
                write_log_rows(pending.drain())
            except Exception:
                # Structured logs still reach stdout even if the DB write fails. Don't stop
                logger.exception("Failed to write logs to the DB")


__all__ = ["DeferredLogWriteMiddleware"]
