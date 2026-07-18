"""FastAPI JWT 認証依存コンポーネント。

``Depends()`` ベースで JWT を検証し、検証済みの ``AuthenticatedPrincipal`` を
ルーターへ渡す。認可は :func:`require_permission`（scope ベース）で宣言する。
"""
from __future__ import annotations

import logging

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.logging.request_context import user_id_hash_var

logger = logging.getLogger(__name__)

# アクセストークンを格納する Cookie 名（ログイン時に auth ルーターが設定する）
ACCESS_TOKEN_COOKIE = "access_token"

# Authorization ヘッダー優先、無ければ Cookie フォールバック
_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    access_token_cookie: str | None,
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return access_token_cookie or None


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    """JWT を検証して ``AuthenticatedPrincipal`` を返す。失敗時は 401。"""
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal, reason = TokenService.verify_access_token_with_reason(token, session=db)
    if not principal:
        logger.debug("JWT 認証失敗: %s", reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": reason},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 以降のログへ user.id_hash を伝播する（PII は残さない）
    user_id_hash_var.set(principal.id_hash)
    return principal


def require_permission(*codes: str):
    """指定された権限を全て保持している場合のみアクセスを許可する依存関数ファクトリ。

    使用例::

        @router.get("/api/admin/users")
        def list_users(
            principal: AuthenticatedPrincipal = Depends(require_permission("user:manage")),
        ):
            ...
    """

    async def _check(
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if not principal.can(*codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"Required permissions: {', '.join(codes)}",
                },
            )
        return principal

    return _check


__all__ = ["get_current_principal", "require_permission", "ACCESS_TOKEN_COOKIE"]
