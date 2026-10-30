"""ログインが成立したときに載せるもの（ADR-0076 §4）。

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

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import object_session

from presentation.fastapi.dependencies.auth import (
    set_access_token_cookie,
    set_logout_token_cookie,
    set_refresh_token_cookie,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE
from presentation.fastapi.schemas.auth import SessionResponse
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.session_carry_over import FRESH_SIGN_IN, SessionCarryOver
from shared.infrastructure.models import User
from shared.infrastructure.tenant_scope import tenant_admits
from shared.kernel.settings.settings import settings


def establish_session(
    response: Response,
    user: User,
    carry: SessionCarryOver = FRESH_SIGN_IN,
) -> SessionResponse:
    """トークン対を発行し、Cookie へ載せて寿命だけを返す。

    ``carry`` は前のセッションから引き継ぐもの（ロール・IdP のセッション・最後に実際に
    サインインした時刻）。⚠ **更新・ロールの切り替えでは必ず全部引き継ぐこと**
    （:mod:`~presentation.fastapi.services.session_carry_over`）。既定は「いま入口から
    入った」で、そのまま使ってよいのはパスワード・パスキーの入口だけ（SSO は IdP の
    セッションを渡す）。
    """
    from presentation.fastapi.services.token_service import TokenService

    ensure_tenant_admits(user)
    pair = TokenService.create_token_pair(user, carry=carry)
    set_access_token_cookie(response, str(pair["access_token"]))
    if _record_refresh_session(user, pair, carry):
        set_refresh_token_cookie(response, str(pair["refresh_token"]))
        set_logout_token_cookie(response, str(pair["logout_token"]))
    _set_csrf_cookie(response)
    return SessionResponse(expires_in=settings.access_token_expires_seconds)


def _record_refresh_session(user: User, pair: dict[str, object], carry: SessionCarryOver) -> bool:
    """控えを作るか振り替える（ADR-0091）。リフレッシュトークンの Cookie を載せてよければ真。"""
    session = object_session(user)
    if session is None:  # pragma: no cover - 入口は全部 DB から読んだ利用者を渡す
        raise RuntimeError("the user must belong to a session")
    session_id, jti = str(pair["refresh_session_id"]), str(pair["refresh_jti"])
    if carry.refresh_session_id is None:
        refresh_sessions.begin(session, session_id=session_id, user_id=user.id, jti=jti)
        return True
    return refresh_sessions.rotate(session, session_id=session_id, new_jti=jti, expected_jti=carry.presented_jti)


TENANT_SUSPENDED = "tenant_suspended"


def ensure_tenant_admits(user: User) -> None:
    """止めたテナントの人にはトークンを出さない（ADR-0079 §1）。入口は全部ここを通る。"""
    session = object_session(user)
    if session is not None and not tenant_admits(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TENANT_SUSPENDED})


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
