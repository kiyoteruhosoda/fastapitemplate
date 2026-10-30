"""notes のドメイン例外 → HTTP 応答（応答本文はエラーコードのみ）。"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.notes.domain.exceptions import (
    NoteError,
    NoteNotFoundError,
    NoteNotOwnedError,
    ShareGroupNotJoinedError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[NoteError], int] = {
    # 読めないメモは「無い」。403 にすると、その ID のメモが在ることを教えてしまう
    NoteNotFoundError: status.HTTP_404_NOT_FOUND,
    NoteNotOwnedError: status.HTTP_403_FORBIDDEN,
    ShareGroupNotJoinedError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def status_for(error: NoteError) -> int:
    return _STATUS_BY_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)


def register_note_error_handler(app: FastAPI) -> None:
    @app.exception_handler(NoteError)
    async def _handle(request: Request, error: NoteError) -> JSONResponse:
        status_code = status_for(error)
        log_failed_request(request, status_code, error.code)
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}})


__all__ = ["register_note_error_handler", "status_for"]
