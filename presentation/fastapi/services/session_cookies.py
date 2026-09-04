"""ログインが成立したときに載せるもの（ADR-0028）。

トークンを発行する経路は 3 本ある（パスワード / パスキー / SSO の券の引き換え）。
**載せ方をここ 1 か所に集める** ——1 本でも Cookie の付け方がずれると、その入口
だけ CSRF が効かない・更新できない、といった差が出る。

⚠ **応答本文にトークンを載せない。** Cookie は自動で送られるので、本文にも返すと
XSS が ``POST /api/auth/refresh`` を叩いて新しいトークンを読めてしまい、
``httpOnly`` にした意味が無くなる。返すのは寿命だけで、SPA はそれを使って
更新の頃合いを測る。
"""

from __future__ import annotations

import secrets

from fastapi import Response

from presentation.fastapi.dependencies.auth import (
    set_access_token_cookie,
    set_refresh_token_cookie,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE
from presentation.fastapi.schemas.auth import SessionResponse
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings


def establish_session(response: Response, user: User, *, active_role: str | None = None) -> SessionResponse:
    """トークン対を発行し、Cookie へ載せて寿命だけを返す。"""
    from presentation.fastapi.services.token_service import TokenService

    pair = TokenService.create_token_pair(user, active_role=active_role)
    set_access_token_cookie(response, str(pair["access_token"]))
    set_refresh_token_cookie(response, str(pair["refresh_token"]))
    _set_csrf_cookie(response)
    return SessionResponse(expires_in=settings.access_token_expires_seconds)


def _set_csrf_cookie(response: Response) -> None:
    """CSRF の二重送信トークン。**これだけは JavaScript から読める。**

    読めなければヘッダーに載せられない。漏れてもそれ単体では何もできない値なので、
    アクセストークンと同じ扱いにしない。
    """
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=settings.refresh_token_expires_seconds,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


__all__ = ["establish_session"]
