"""Catch unexpected exceptions inside the middleware stack as ordinary responses.

An ``Exception`` handler alone is not enough. Starlette mounts it on ``ServerErrorMiddleware``
(**outside** all middleware), so a response built there passes through neither the CORS
middleware nor the request logging middleware. As a result:

- A frontend on another origin gets no ``Access-Control-Allow-Origin``, and the browser
  discards the body. The error code is never read and falls back to ``unknown_error``.
- No 500 line is left in the access log (the exception bypasses the logging layer).
- The batched app/audit log writes don't run, and all log rows from that request are lost
  (the batching middleware is outside too).

Placing this middleware innermost and turning the exception into a response here makes it look
like "an ordinary 500 response" to the middleware further out.

**Written as a plain ASGI middleware** (not ``BaseHTTPMiddleware``). ``BaseHTTPMiddleware`` runs
the downstream in **a separate task**, so ``contextvars`` set there don't propagate to
``dispatch``. ``user_id_hash`` set by the auth dependency
(:mod:`shared.kernel.logging.request_context`) is exactly that case: with ``BaseHTTPMiddleware``,
only the 500 log lines would lack "whose request it was". ``await self.app(...)`` waits for the
downstream in the same task, so the authenticated context carries into the record.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from presentation.fastapi.error_handling import (
    internal_error_response,
    log_unhandled_exception,
)


class InternalErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = _ResponseStarted()
        try:
            await self.app(scope, receive, started.watching(send))
        except Exception as error:
            # This is the last resort, so catch any kind here and turn it into a response.
            request = Request(scope)
            if started.value:
                # The response cannot be replaced once headers are sent. Just record it and
                # re-raise (the outer ServerErrorMiddleware closes the connection).
                log_unhandled_exception(request, error)
                raise
            response = internal_error_response(request, error)
            await response(scope, receive, send)


class _ResponseStarted:
    """Remember whether sending the response has started (used to decide if it can be replaced)."""

    def __init__(self) -> None:
        self.value = False

    def watching(self, send: Send) -> Send:
        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.value = True
            await send(message)

        return _send


__all__ = ["InternalErrorMiddleware"]
