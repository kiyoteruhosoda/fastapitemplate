"""ドメイン例外 -> HTTP 応答の対応付け。

ここが受けるのは **JSON を返す経路**（``POST /api/auth/sso/token``・
``POST /api/auth/sso/backchannel-logout``・``/api/auth/sso/link`` の 3 つ）だけ。
ブラウザの画面遷移で使う ``/login`` と ``/callback`` はルーター自身が例外を捕まえ、
ログイン画面への転送に変える（JSON を返しても SPA は読めないため）。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityFederationError,
    IdentityProviderUnavailableError,
    InvalidLogoutTokenError,
    SsoAlreadyLinkedError,
    SsoIdentityNotLinkedError,
    SsoIdentityTakenError,
    SsoLastEntranceError,
    SsoNotConfiguredError,
    SsoTicketNotFoundError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[IdentityFederationError], int] = {
    IdentityProviderUnavailableError: status.HTTP_502_BAD_GATEWAY,
    SsoNotConfiguredError: status.HTTP_404_NOT_FOUND,
    SsoTicketNotFoundError: status.HTTP_401_UNAUTHORIZED,
    # 停止の通知を送るのは IdP であって利用者ではない。401 で返すと「認証し直せ」に
    # 読めてしまうので、仕様どおり「要求が不正」として返す（Back-Channel Logout 1.0 §2.8）。
    InvalidLogoutTokenError: status.HTTP_400_BAD_REQUEST,
    # 連携の解除・結び付け（ADR-0040）。⚠ **401 で返さない** ——呼んでいる本人は
    # 認証を通っており、「認証し直せ」と読めると利用者が無意味な操作を繰り返す。
    SsoIdentityNotLinkedError: status.HTTP_404_NOT_FOUND,
    SsoIdentityTakenError: status.HTTP_409_CONFLICT,
    SsoAlreadyLinkedError: status.HTTP_409_CONFLICT,
    SsoLastEntranceError: status.HTTP_409_CONFLICT,
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
