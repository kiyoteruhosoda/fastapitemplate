"""アプリ（assay に直接ログインした Android アプリ）からの呼び出しを受ける関門（ADR-0045）。

⚠ **アプリのトークンで通るのは、この依存関数を付けたルータだけ**（「アプリから叩いてよい」と
宣言したもの）。管理・アカウント・トークンの出し直しの口は、これまでどおり
:func:`presentation.fastapi.dependencies.auth.get_current_principal`（このアプリのトークンだけ）。
⚠ **``APP_CLIENT_IDS`` が空なら、assay のトークンは 1 本も受けない**（1 と同じ振る舞いになる）。

順に、

1. このアプリが発行したトークン（Web の Cookie / ヘッダー）ならそのまま通す
2. ``Authorization: Bearer`` で来た assay のアクセストークンなら、受け取れるか確かめて利用者へ落とす
   ——権限は**毎回 DB から**引く（assay のトークンには載っていない）
3. どちらでもなければ、1 と同じ 401
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from bounded_contexts.identity_federation.application.use_cases.authenticate_app_access_token import (
    AppTokenAcceptance,
    AuthenticateAppAccessToken,
)
from bounded_contexts.identity_federation.domain.services.app_token_gateway import AppTokenGateway
from bounded_contexts.identity_federation.infrastructure.httpx_app_token_gateway import HttpxAppTokenGateway
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from bounded_contexts.identity_federation.presentation.dependencies import (
    DbDep,
    claims_mapping,
    resolve_federated_account,
)
from presentation.fastapi.dependencies.auth import (
    ACCESS_TOKEN_COOKIE,
    _bearer_scheme,
    get_current_principal,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.kernel.logging.request_context import actor_user_id_var, user_id_hash_var
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

_app_token_gateway = HttpxAppTokenGateway()


def app_token_gateway() -> AppTokenGateway:
    return _app_token_gateway


AppTokenGatewayDep = Annotated[AppTokenGateway, Depends(app_token_gateway)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def authenticate_app_access_token(db: DbDep, gateway: AppTokenGatewayDep) -> AuthenticateAppAccessToken:
    return AuthenticateAppAccessToken(
        acceptance=AppTokenAcceptance(issuer=settings.oidc_issuer, client_ids=settings.app_client_ids),
        gateway=gateway,
        identities=SqlFederatedIdentityRepository(db),
        revocations=SqlSessionRevocationRepository(db),
        claims=claims_mapping(),
        accounts=resolve_federated_account(db),
    )


AuthenticateDep = Annotated[AuthenticateAppAccessToken, Depends(authenticate_app_access_token)]


def _is_our_token(token: str) -> bool:
    from presentation.fastapi.services.token_service import TokenService

    principal, _ = TokenService.verify_access_token_with_reason(token)
    return principal is not None


def _principal_of(user: User) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=user.id,
        email=user.email,
        username=user.username,
        permissions=frozenset(user.permission_codes_of(None)),
    )
    user_id_hash_var.set(principal.id_hash)
    actor_user_id_var.set(principal.user_id)
    return principal


async def get_app_or_web_principal(
    credentials: BearerDep,
    authenticate: AuthenticateDep,
    db: DbDep,
    access_token_cookie: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> AuthenticatedPrincipal:
    bearer = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
    if bearer is None or _is_our_token(bearer) or not settings.app_client_ids:
        return await get_current_principal(credentials, access_token_cookie)
    user = db.get(User, authenticate.execute(bearer))
    if user is None or not user.is_active:
        logger.info("app_access_token_user_inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _principal_of(user)


AppOrWebPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_app_or_web_principal)]

__all__ = ["AppOrWebPrincipalDep", "app_token_gateway", "get_app_or_web_principal"]
