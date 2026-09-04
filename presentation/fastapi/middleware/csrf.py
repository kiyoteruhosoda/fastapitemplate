"""Cookie で認証したリクエストの CSRF 対策（二重送信トークン。ADR-0028）。

トークンを httpOnly Cookie に移すと、ブラウザは**こちらが送るつもりの無い
リクエストにも Cookie を付ける**ようになる。`SameSite=Lax` は別サイトからの
POST を止めるが、同一サイト扱いになる相手（サブドメインを取られた場合など）は
止めない。更新系だけ、Cookie とヘッダーの両方に同じ値を求める。

**要求するのは「Cookie で認証している更新系」だけ。**

- 読み取り（GET / HEAD / OPTIONS）は求めない。結果を攻撃者が読めないため。
- ``Authorization`` ヘッダーで来たリクエストは求めない。**ヘッダーは自動では
  送られない**ので、そもそも CSRF が成立しない（curl・CI・他アプリのため）。
- **入口そのもの（ログイン・パスキー・SSO の引き換え・パスワード再設定・ログアウト）は
  求めない。** これらは既にあるセッションに対して何かをするのではなく、セッションを
  作る／捨てる操作である。ここで求めると、**別のアカウントでログインし直すだけで
  403 になる**（前のセッションの Cookie が残っているため）。ログイン CSRF の心配は
  残るが、パスワードでのログインには資格情報が要り、SSO は往復状態の Cookie で
  別に塞いでいる（ADR-0025）。ログアウトは Cookie を落とすだけで害が小さい。

トークンは JavaScript から読めなければ送れないので、この Cookie だけは
``httpOnly`` にしない。**アクセストークンとは別物**である ——こちらは漏れても
それ単体では何もできない。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from presentation.fastapi.dependencies.auth import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
ERROR_CODE = "csrf_token_invalid"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: セッションを作る／捨てる口。既存のセッションに対する操作ではないので対象外。
_ENTRANCES = frozenset(
    {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/passkey/challenge",
        "/api/auth/passkey/login",
        "/api/auth/sso/token",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    }
)


def _authenticated_by_cookie(request: Request) -> bool:
    if request.headers.get("Authorization"):
        return False
    return bool(request.cookies.get(ACCESS_TOKEN_COOKIE) or request.cookies.get(REFRESH_TOKEN_COOKIE))


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in _SAFE_METHODS or request.url.path in _ENTRANCES or not _authenticated_by_cookie(request):
            return await call_next(request)
        sent = request.headers.get(CSRF_HEADER) or ""
        expected = request.cookies.get(CSRF_COOKIE) or ""
        # 一致だけでなく**空でないこと**も見る。両方が空のときに通すと、Cookie を
        # 落とした相手が素通りする。
        if not expected or not compare_digest(sent, expected):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": {"error": ERROR_CODE}},
            )
        return await call_next(request)


__all__ = ["CSRF_COOKIE", "CSRF_HEADER", "ERROR_CODE", "CsrfMiddleware"]
