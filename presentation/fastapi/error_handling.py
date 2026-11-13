"""Recording failed responses, and mapping unexpected exceptions to HTTP responses (last resort).

**Failures turn into responses outside the router.** ``HTTPException``, input validation errors
and domain exceptions all leave the router when raised, and an exception handler builds the
response. So adding a ``logger`` to a router doesn't record failures, and the app log holds only
the single access log line (status code only). "What happened" (error code, fields that failed
validation, traceback) is known only in the handler.

So failure recording is centralized here. Routers need no ``try/except`` of their own, and the
recording granularity is decided in one place. :func:`log_level_for_status` picks the log level
from the status code (the access log uses the same function).

For unexpected exceptions, this also builds the response. Without a catch-all, Starlette returns
a **text/plain** body ``Internal Server Error``. The API client (SPA) reads bodies as JSON, so it
could not extract an error code and could only show the generic ``unknown_error`` message (and
the cause could not be narrowed down). So this

- normalizes it to JSON ``{"detail": {"error": "internal_error"}}`` (the frontend decides the
  display text; CLAUDE.md "Internationalization")
- logs it with the traceback (stored in the ``trace`` column of the ``log`` table)

Mapping domain exceptions is each context's ``error_handling``'s job, so don't add individual
exceptions here (use :func:`log_failed_request` for recording).

The catch-all is placed **twice**.

1. :class:`~presentation.fastapi.middleware.internal_error.InternalErrorMiddleware`
   (the normal path). It sits **inside** CORS and request logging, so the response gets CORS
   headers and ``X-Request-Id``, and the access log records it as 500.
2. The ``Exception`` handler (safety net). Only works when middleware outside 1 itself fails.
   Starlette mounts this handler on ``ServerErrorMiddleware`` (outside all middleware), so
   responses returned from it have no CORS headers. That is why the normal path is left to 1.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from shared.kernel.logging.request_context import current_request_id

logger = logging.getLogger(__name__)

INTERNAL_ERROR_CODE = "internal_error"

# 401 happens routinely (expired tokens, API calls without login), so only it drops to INFO.
# Other 4xx are "a mistaken assumption by the user or caller" and go up to WARNING so they
# don't get buried when filtering logs.
_ROUTINE_STATUS_CODES = frozenset({status.HTTP_401_UNAUTHORIZED})

# Input validation failure (the status FastAPI returns). ``status``'s
# ``HTTP_422_UNPROCESSABLE_ENTITY`` is deprecated in Starlette and merely referencing it
# emits a warning, so the number is held here.
_VALIDATION_ERROR_STATUS = 422


def log_level_for_status(status_code: int) -> int:
    """Decide the log level from the HTTP status code.

    The access log (``RequestLoggingMiddleware``) and failure recording (this module) share
    the same policy, so the decision lives here only.
    """
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return logging.ERROR
    if status_code >= status.HTTP_400_BAD_REQUEST and status_code not in _ROUTINE_STATUS_CODES:
        return logging.WARNING
    return logging.INFO


def error_code_of(detail: object) -> str | None:
    """Extract only the error code from the response body (``detail``).

    This app's responses are uniformly ``{"error": "..."}``. Plain strings such as FastAPI's
    default ``"Not Found"`` are taken as is. **Nothing but the code is extracted**: ``detail`` may
    contain a target's name, and copying values into logs would leak PII.
    """
    if isinstance(detail, dict):
        code = detail.get("error")
        return str(code) if code is not None else None
    if isinstance(detail, str):
        return detail
    return None


def log_failed_request(request: Request, status_code: int, error_code: str | None) -> None:
    """Record that an error response is being returned. Also called from domain exception handlers.

    The error code **goes into the message**. Only the columns (``message`` / ``path`` /
    ``method`` / ``status_code`` / ``trace``) are kept in the ``log`` table; the rest of ``extra``
    only appears in the stdout JSON. It is put in the message so the admin console can show
    "which code it failed with".
    """
    logger.log(
        log_level_for_status(status_code),
        "request_failed: %s",
        error_code or "unknown",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "error_code": error_code,
        },
    )


def log_unhandled_exception(request: Request, error: Exception) -> None:
    """Record an unexpected exception with its traceback (stored in the ``trace`` column of ``log``)."""
    logger.exception(
        "unhandled_exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
        exc_info=error,
    )


def internal_error_response(request: Request, error: Exception) -> JSONResponse:
    """Record the exception and build a 500 response that returns only the error code.

    The exception details are not exposed in the response (to avoid revealing internals).
    Tracing is done via ``requestId``.
    """
    log_unhandled_exception(request, error)
    request_id = current_request_id()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": {"error": INTERNAL_ERROR_CODE}},
        headers={"X-Request-Id": request_id} if request_id else None,
    )


def _validation_failures(error: RequestValidationError) -> str:
    """List fields that failed validation as ``body.email:missing``.

    **Input values themselves are not included** (including ``ctx`` or ``input`` would copy email
    addresses and passwords into logs; CLAUDE.md "Logging"). Field names and failure reasons are
    enough to trace which request was wrong and how.
    """
    return ",".join(
        "{}:{}".format(
            ".".join(str(part) for part in item.get("loc", ())),
            item.get("type", "invalid"),
        )
        for item in error.errors()
    )


def register_error_handling(app: FastAPI) -> None:
    """Register failure recording and the safety net for exceptions raised outside the middleware."""

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, error: StarletteHTTPException) -> Response:
        log_failed_request(request, error.status_code, error_code_of(error.detail))
        return await http_exception_handler(request, error)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, error: RequestValidationError) -> Response:
        invalid_fields = _validation_failures(error)
        logger.warning(
            "request_validation_failed: %s",
            invalid_fields,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": _VALIDATION_ERROR_STATUS,
                "invalid_fields": invalid_fields,
            },
        )
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, error: Exception) -> JSONResponse:
        return internal_error_response(request, error)


__all__ = [
    "INTERNAL_ERROR_CODE",
    "error_code_of",
    "internal_error_response",
    "log_failed_request",
    "log_level_for_status",
    "log_unhandled_exception",
    "register_error_handling",
]
