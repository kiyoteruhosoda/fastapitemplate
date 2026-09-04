"""認可要求の往復状態を、署名付き Cookie で運ぶ（ADR-0025）。

``state`` / ``nonce`` / PKCE の ``code_verifier`` は、リダイレクトで IdP へ離れて
戻ってくる**その間だけ**必要になる。サーバー側に控えを置くと、この短命な値のために
表と掃除が要るうえ、控えは全員で 1 つの表を共有するので「``state`` を知っている
だけの相手」でも戻りを完了できてしまう（ログイン CSRF）。**改竄できない形で
ブラウザに預ける**ほうが、同じ防御を 1 つの仕組みで達成できる ——Cookie が無ければ
照合対象そのものが存在しない。

- 署名は内蔵 JWT と同じ ``JWT_SECRET_KEY``（HS256）。中身は読めるが**書き換えられない**。
- 有効期限は短く（``OIDC_LOGIN_TRANSACTION_TTL_SECONDS``）。
- ``HttpOnly``。``code_verifier`` を持つので JavaScript から読めてはならない。
- ``SameSite=Lax`` にするのは、IdP からの戻りが**別サイトからの GET の画面遷移**
  だから（``Strict`` だと戻ってきた時点で送られず、正規のログインが必ず失敗する）。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from fastapi import Response

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow

COOKIE_NAME = "sso_tx"
_ALGORITHM = "HS256"


def issue(response: Response, transaction: LoginTransaction, *, path: str) -> None:
    """往復状態を署名して Cookie へ載せる。"""
    ttl = settings.oidc_login_transaction_ttl_seconds
    payload: dict[str, Any] = {
        "state": transaction.state,
        "nonce": transaction.nonce,
        "code_verifier": transaction.code_verifier,
        "redirect_to": transaction.redirect_to,
        "exp": utcnow() + timedelta(seconds=ttl),
    }
    response.set_cookie(
        COOKIE_NAME,
        jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM),
        max_age=ttl,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=path,
    )


def read(raw: str | None) -> LoginTransaction | None:
    """Cookie から往復状態を復元する。**復元できないものは黙って `None`。**

    署名が合わない・期限が切れた・そもそも無い、のいずれも呼び出し側から見れば
    「この戻りは受け付けられない」という 1 つの結果になる（区別しても利用者に
    返せる情報が増えるわけではなく、攻撃者に手掛かりを与えるだけ）。
    """
    if not raw:
        return None
    try:
        claims = jwt.decode(raw, settings.jwt_secret_key, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    values = {key: claims.get(key) for key in ("state", "nonce", "code_verifier", "redirect_to")}
    if not all(isinstance(value, str) and value for value in values.values()):
        return None
    return LoginTransaction(**values)  # type: ignore[arg-type]


def clear(response: Response, *, path: str) -> None:
    """往復が終わったので落とす（成功・失敗どちらでも）。"""
    response.delete_cookie(COOKIE_NAME, path=path)


__all__ = ["COOKIE_NAME", "clear", "issue", "read"]
