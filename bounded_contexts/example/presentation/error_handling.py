"""example のドメイン例外 → HTTP 応答（応答本文はエラーコードのみ）。"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.example.domain.exceptions import DomainError, ItemNotFoundError
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    ItemNotFoundError: status.HTTP_404_NOT_FOUND,
}


def register_item_error_handler(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle(request: Request, error: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)
        log_failed_request(request, status_code, error.code)
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}})


__all__ = ["register_item_error_handler"]
