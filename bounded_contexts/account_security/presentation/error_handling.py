"""ドメイン例外 → HTTP 応答の対応付け。

ルーターごとに ``try/except`` を書き散らさないよう、アプリケーション全体の
例外ハンドラとして一度だけ登録する。応答本文はエラーコードのみで、表示文言は
フロントエンドが決める（CLAUDE.md「国際化」）。

失敗の記録は横断的な受け皿（:func:`~presentation.fastapi.error_handling.log_failed_request`）
へ委ねる。ここで独自に記録すると、``HTTPException`` 由来の失敗とレベルや
フィールドの揃わない行が混ざり、ログを絞り込めなくなる。
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.account_security.domain.exceptions import (
    AccountSecurityError,
    ChallengeNotFoundError,
    InvalidTotpCodeError,
    PasskeyAlreadyRegisteredError,
    PasskeyNotFoundError,
    PasskeyVerificationError,
    TotpAlreadyEnabledError,
    TotpNotEnrolledError,
    TotpRequiredError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[AccountSecurityError], int] = {
    ChallengeNotFoundError: status.HTTP_400_BAD_REQUEST,
    InvalidTotpCodeError: status.HTTP_400_BAD_REQUEST,
    PasskeyAlreadyRegisteredError: status.HTTP_409_CONFLICT,
    PasskeyNotFoundError: status.HTTP_404_NOT_FOUND,
    PasskeyVerificationError: status.HTTP_401_UNAUTHORIZED,
    TotpAlreadyEnabledError: status.HTTP_409_CONFLICT,
    TotpNotEnrolledError: status.HTTP_409_CONFLICT,
    TotpRequiredError: status.HTTP_401_UNAUTHORIZED,
}


def status_for(error: AccountSecurityError) -> int:
    return _STATUS_BY_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)


def register_account_security_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AccountSecurityError)
    async def _handle(request: Request, error: AccountSecurityError) -> JSONResponse:
        status_code = status_for(error)
        log_failed_request(request, status_code, error.code)
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}})


__all__ = ["register_account_security_error_handler", "status_for"]
