"""Per-request structured logging (assigning and propagating ``requestId``).

The assigned ``requestId`` is also put in the response header (``X-Request-Id``). Both app logs
(``log``) and audit logs (``audit_log``) carry the same value, so an ID received from a user lets
you trace "what happened in that request" from both sides.

The client (IP, User-Agent) is propagated as well. Audit logs record these values, and passing
them around as handler arguments would spread to every router
(:mod:`shared.kernel.logging.request_context`).

The log level follows the response status code
(:func:`~presentation.fastapi.error_handling.log_level_for_status`). Listing only successes at
INFO hides anomalies, so 4xx is WARNING and 5xx is ERROR; filtering by level leaves only
failures.

**Written as a plain ASGI middleware** (not ``BaseHTTPMiddleware``). ``BaseHTTPMiddleware`` runs
the downstream in **a separate task**, so ``user_id_hash`` set by the auth dependency doesn't
come back to the logging side, and only the ``http_request`` line lacks "whose request it was"
(same reason as :mod:`presentation.fastapi.middleware.internal_error`).

The line is emitted **when the start of the response is sent**, without waiting for the
downstream to finish. Even when streaming a large file, ``duration_ms`` is the time to the first
byte, and the line survives a dropped connection.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette import status
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from presentation.fastapi.error_handling import log_level_for_status
from shared.kernel.logging.request_context import (
    actor_user_id_var,
    ip_address_var,
    request_id_var,
    user_agent_var,
    user_id_hash_var,
)
from shared.kernel.settings.settings import settings

access_logger = logging.getLogger("app.request")

_FORWARDED_FOR_HEADER = "x-forwarded-for"

# Periodic liveness and metrics scraping. Docker's healthcheck hits every few tens of seconds,
# so keeping successes would flood the app log and push out the lines that matter (each one
# carries no information beyond "nothing was wrong").
# **Failures (4xx/5xx) are kept.** A failing probe is exactly what we want to know, and
# dropping it here would leave the monitored thing unmonitored.
_PROBE_PATHS = frozenset({"/api/health", "/healthz", "/readyz", "/metrics"})


def _should_log(path: str, status_code: int) -> bool:
    return status_code >= status.HTTP_400_BAD_REQUEST or path not in _PROBE_PATHS


def _client_ip(request: Request) -> str | None:
    """Return the client IP. It ends up in the audit log, so leave no path for spoofing.

    ``X-Forwarded-For`` is **a header the sender can set freely**, and the bundled nginx's
    ``$proxy_add_x_forwarded_for`` appends the actual client after the received value. Taking the
    leftmost value would let anyone record an arbitrary IP just by sending
    ``X-Forwarded-For: 1.2.3.4``.

    So only the number of hops declared in ``TRUSTED_PROXY_HOPS`` is trusted, taking the value at
    that position counted from the right (a value the proxy appended itself = cannot be spoofed).
    The default is 0, which ignores the header entirely and uses the TCP peer.
    """
    client_host = request.client.host if request.client else None

    hops = settings.trusted_proxy_hops
    if hops <= 0:
        return client_host

    forwarded = request.headers.get(_FORWARDED_FOR_HEADER)
    if not forwarded:
        return client_host
    addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(addresses) < hops:
        # Fewer than the declared hops = not the expected path. Don't trust the header.
        return client_host
    return addresses[-hops]


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        # Explicitly reset per request so values from the previous request don't linger
        user_id_hash_var.set(None)
        actor_user_id_var.set(None)
        ip_address_var.set(_client_ip(request))
        user_agent_var.set(request.headers.get("user-agent"))
        start = time.perf_counter()

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code = message["status"]
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                if _should_log(request.url.path, status_code):
                    access_logger.log(
                        log_level_for_status(status_code),
                        "http_request",
                        extra={
                            "request_id": request_id,
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": status_code,
                            "duration_ms": duration_ms,
                        },
                    )
                MutableHeaders(scope=message)["X-Request-Id"] = request_id
            await send(message)

        await self.app(scope, receive, _send)


__all__ = ["RequestLoggingMiddleware"]
