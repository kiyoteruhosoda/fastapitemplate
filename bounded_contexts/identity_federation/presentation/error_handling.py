"""ドメイン例外 -> HTTP 応答の対応付け。

ここが受けるのは **JSON を返す経路**（``POST /api/auth/sso/token``）だけ。
ブラウザの画面遷移で使う ``/login`` と ``/callback`` はルーター自身が例外を捕まえ、
ログイン画面への転送に変える（JSON を返しても SPA は読めないため）。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityFederationError,
    IdentityProviderUnavailableError,
    SsoNotConfiguredError,
    SsoTicketNotFoundError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[IdentityFederationError], int] = {
    IdentityProviderUnavailableError: status.HTTP_502_BAD_GATEWAY,
    SsoNotConfiguredError: status.HTTP_404_NOT_FOUND,
    SsoTicketNotFoundError: status.HTTP_401_UNAUTHORIZED,
}


def status_for(error: IdentityFederationError) -> int:
    """既定は 401。SSO の失敗はどれもログインが通らなかったことを意味する。"""
    return _STATUS_BY_ERROR.get(type(error), status.HTTP_401_UNAUTHORIZED)


def register_identity_federation_error_handler(app: FastAPI) -> None:
    @app.exception_handler(IdentityFederationError)
    async def _handle(request: Request, error: IdentityFederationError) -> JSONResponse:
        status_code = status_for(error)
        log_failed_request(request, status_code, error.code)
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}})


__all__ = ["register_identity_federation_error_handler", "status_for"]
