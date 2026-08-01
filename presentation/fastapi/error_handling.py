"""失敗した応答の記録と、想定外の例外 → HTTP 応答の対応付け（最後の受け皿）。

**失敗はルーターの外側で応答へ変わる。** ``HTTPException`` も入力検証エラーも
ドメイン例外も、送出された時点でルーターを抜け、例外ハンドラが応答を組み立てる。
そのためルーターに ``logger`` を足しても失敗は記録されず、アプリログには
アクセスログの 1 行（ステータスコードだけ）しか残らない。「何が起きたか」——
エラーコード・入力検証で落ちた項目・traceback —— はハンドラでしか分からない。

そこで失敗の記録をここへ集約する。ルーターごとに ``try/except`` を書かずに済み、
記録の粒度も 1 か所で決められる。ログのレベルは :func:`log_level_for_status` が
ステータスコードから決める（アクセスログも同じ関数を使う）。

想定外の例外については応答も組み立てる。受け皿が無いと Starlette は本文
``Internal Server Error`` の **text/plain** を返す。API クライアント（SPA）は
本文を JSON として読むため、これを受け取るとエラーコードを取り出せず、画面には
一律 ``unknown_error`` の文言しか出せない（原因の切り分けもできない）。そこで

- ``{"detail": {"error": "internal_error"}}`` の JSON へ揃え（表示文言は
  フロントエンドが決める。CLAUDE.md「国際化」）
- traceback つきでログへ残す（``log`` テーブルの ``trace`` 列へ入る）

を行う。ドメイン例外の対応付けは各コンテキストの ``error_handling`` が担うので、
ここへ個別の例外を足さない（記録には :func:`log_failed_request` を使う）。

受け皿は**二重**に置く。

1. :class:`~presentation.fastapi.middleware.internal_error.InternalErrorMiddleware`
   （通常の経路）。CORS・リクエストログの**内側**に置くため、応答に CORS
   ヘッダーと ``X-Request-Id`` が付き、アクセスログにも 500 として残る。
2. ``Exception`` ハンドラ（保険）。1 より外側のミドルウェア自身が落ちた場合に
   だけ働く。Starlette はこのハンドラを ``ServerErrorMiddleware``（全ミドル
   ウェアの外側）へ載せるため、ここから返す応答には CORS ヘッダーが付かない。
   通常の経路を 1 に任せているのはこのため。
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

# 401 は運用上ふつうに起きる（トークンの期限切れ・未ログインでの API 呼び出し）。
# ここだけ INFO へ落とす。残りの 4xx は「利用者か呼び出し側の想定違い」として
# WARNING に上げ、ログを絞り込んだときに埋もれないようにする。
_ROUTINE_STATUS_CODES = frozenset({status.HTTP_401_UNAUTHORIZED})

# 入力検証の失敗（FastAPI が返すステータス）。``status`` の
# ``HTTP_422_UNPROCESSABLE_ENTITY`` は Starlette で非推奨になり、参照するだけで
# 警告が出るためここで数値を持つ。
_VALIDATION_ERROR_STATUS = 422


def log_level_for_status(status_code: int) -> int:
    """HTTP のステータスコードからログのレベルを決める。

    アクセスログ（``RequestLoggingMiddleware``）と失敗の記録（このモジュール）で
    同じ方針を使うため、判断はここに 1 つだけ置く。
    """
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return logging.ERROR
    if status_code >= status.HTTP_400_BAD_REQUEST and status_code not in _ROUTINE_STATUS_CODES:
        return logging.WARNING
    return logging.INFO


def error_code_of(detail: object) -> str | None:
    """応答本文（``detail``）からエラーコードだけを取り出す。

    このアプリの応答は ``{"error": "..."}`` で揃っている。FastAPI 既定の
    ``"Not Found"`` のような文字列もそのまま扱う。**コード以外は取り出さない**——
    ``detail`` には対象の名前が入ることがあり、値をログへ移すと PII になるため。
    """
    if isinstance(detail, dict):
        code = detail.get("error")
        return str(code) if code is not None else None
    if isinstance(detail, str):
        return detail
    return None


def log_failed_request(request: Request, status_code: int, error_code: str | None) -> None:
    """エラー応答を返すことを記録する。ドメイン例外のハンドラからも呼ぶ。

    エラーコードは**本文（message）に入れる**。``log`` テーブルへ残るのは
    列にある項目（``message`` / ``path`` / ``method`` / ``status_code`` / ``trace``）
    だけで、``extra`` の残りは stdout の JSON にしか出ない。管理画面から
    「何のコードで落ちたか」を読めるようにするため、本文にも持たせる。
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


def internal_error_response(request: Request, error: Exception) -> JSONResponse:
    """例外を記録し、エラーコードだけを返す 500 応答を組み立てる。

    例外の中身は応答に出さない（内部構造の露出を避ける）。追跡は ``requestId``
    で行う。
    """
    logger.exception(
        "unhandled_exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
        exc_info=error,
    )
    request_id = current_request_id()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": {"error": INTERNAL_ERROR_CODE}},
        headers={"X-Request-Id": request_id} if request_id else None,
    )


def _validation_failures(error: RequestValidationError) -> str:
    """検証に落ちた項目を ``body.email:missing`` の形で並べる。

    **入力値そのものは含めない**（``ctx`` や ``input`` を入れるとメールアドレス・
    パスワードがログへ移る。CLAUDE.md「ログ」）。項目名と落ちた理由だけを残せば、
    どのリクエストがどう間違っていたかは十分に追える。
    """
    return ",".join(
        "{}:{}".format(
            ".".join(str(part) for part in item.get("loc", ())),
            item.get("type", "invalid"),
        )
        for item in error.errors()
    )


def register_error_handling(app: FastAPI) -> None:
    """失敗の記録と、ミドルウェアより外側で起きた例外のための保険を登録する。"""

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
    "register_error_handling",
]
