"""notification のドメイン例外 → HTTP 応答（応答本文はエラーコードのみ）。"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.notification.domain.exceptions import (
    AudienceNotFoundError,
    NotificationError,
    NotificationNotFoundError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[NotificationError], int] = {
    NotificationNotFoundError: status.HTTP_404_NOT_FOUND,
    AudienceNotFoundError: status.HTTP_404_NOT_FOUND,
}


def status_for(error: NotificationError) -> int:
    return _STATUS_BY_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)


def register_notification_error_handler(app: FastAPI) -> None:
    @app.exception_handler(NotificationError)
    async def _handle(request: Request, error: NotificationError) -> JSONResponse:
        status_code = status_for(error)
        log_failed_request(request, status_code, error.code)
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}})


__all__ = ["register_notification_error_handler", "status_for"]
