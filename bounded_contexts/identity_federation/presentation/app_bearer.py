"""アプリ（assay に直接ログインした Android アプリ）からの呼び出しを受ける関門（ADR-0081 §1）。

⚠ **アプリのトークンで通るのは、この依存関数を付けたルータだけ**（「アプリから叩いてよい」と
宣言したもの）。管理・アカウント・トークンの出し直しの口は、これまでどおり
:func:`presentation.fastapi.dependencies.auth.get_current_principal`（このアプリのトークンだけ）。
⚠ **``APP_CLIENT_IDS`` が空なら、assay のトークンは 1 本も受けない**（1 と同じ振る舞いになる）。

順に、

1. このアプリが発行したトークン（Web の Cookie / ヘッダー）ならそのまま通す
2. ``Authorization: Bearer`` で来た assay のアクセストークンなら、受け取れるか確かめて利用者へ落とす
   ——権限は**毎回 DB から**引く（assay のトークンには載っていない）
3. ``Authorization: DPoP`` で来たら、``DPoP`` ヘッダーの証明と一緒に確かめる（ADR-0103）。
   ``cnf.jkt`` のある（端末の鍵に結び付けた）トークンは、この形でしか通らない
4. どちらでもなければ、1 と同じ 401
"""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from bounded_contexts.identity_federation.application.use_cases.authenticate_app_access_token import (
    AppTokenAcceptance,
    AuthenticateAppAccessToken,
)
from bounded_contexts.identity_federation.domain.services.app_token_gateway import AppTokenGateway
from bounded_contexts.identity_federation.domain.value_objects.presented_app_token import PresentedAppToken
from bounded_contexts.identity_federation.infrastructure.httpx_app_token_gateway import HttpxAppTokenGateway
from bounded_contexts.identity_federation.infrastructure.pyjwt_dpop_proof_verifier import PyJwtDpopProofVerifier
from bounded_contexts.identity_federation.infrastructure.sql_dpop_proof_replay_repository import (
    SqlDpopProofReplayRepository,
)
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
    get_operation_principal,
    refuse_during_two_factor_setup,
    refuse_machine,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.infrastructure.tenant_directory import tenant_issuing
from shared.infrastructure.tenant_scope import tenant_admits
from shared.kernel.logging.request_context import actor_user_id_var, user_id_hash_var
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

_app_token_gateway = HttpxAppTokenGateway()
_dpop_proof_verifier = PyJwtDpopProofVerifier()
#: ``Authorization: DPoP <token>``（RFC 9449 §7.1）。``HTTPBearer`` は ``Bearer`` しか読まないので自分で読む。
_DPOP_SCHEME = "dpop "


def app_token_gateway() -> AppTokenGateway:
    return _app_token_gateway


AppTokenGatewayDep = Annotated[AppTokenGateway, Depends(app_token_gateway)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def authenticate_app_access_token(db: Session, gateway: AppTokenGateway, token: str) -> AuthenticateAppAccessToken:
    """トークンの発行者のテナントで受ける（ADR-0079 §4）。登録の無い発行者なら受けない。

    ⚠ 発行者は署名を確かめる前に読むが、**その値は鍵を選ぶのにしか使わない**。登録のある
    発行者を名乗っても、署名はその発行者の鍵でしか通らない。
    """
    tenant = tenant_issuing(db, _unverified_issuer_of(token))
    issuer = tenant.issuer or "" if tenant is not None and tenant.is_active else ""
    return AuthenticateAppAccessToken(
        acceptance=AppTokenAcceptance(issuer=issuer, client_ids=settings.app_client_ids),
        gateway=gateway,
        identities=SqlFederatedIdentityRepository(db),
        revocations=SqlSessionRevocationRepository(db),
        claims=claims_mapping(),
        accounts=resolve_federated_account(db, issuer),
        dpop_proofs=_dpop_proof_verifier,
        dpop_replays=SqlDpopProofReplayRepository(db),
    )


def _unverified_issuer_of(token: str) -> str:
    try:
        issuer = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.InvalidTokenError:
        return ""
    return issuer if isinstance(issuer, str) else ""


def _is_our_token(token: str) -> bool:
    from presentation.fastapi.services.token_service import TokenService

    principal, _ = TokenService.verify_access_token_with_reason(token)
    return principal is not None


def _principal_of_app_token(
    db: Session, gateway: AppTokenGateway, presented: PresentedAppToken
) -> AuthenticatedPrincipal:
    user = db.get(User, authenticate_app_access_token(db, gateway, presented.token).execute(presented))
    if user is None or not user.is_active or not tenant_admits(db, user):
        logger.info("app_access_token_user_inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthenticatedPrincipal(
        user_id=user.id,
        email=user.email,
        username=user.username,
        permissions=frozenset(user.permission_codes_of(None)),
        tenant_id=user.tenant_id,
    )


def _dpop_token(authorization: str | None) -> str | None:
    """``Authorization: DPoP <token>`` のトークン。``DPoP`` の方式でなければ ``None``。"""
    if authorization is None or not authorization.lower().startswith(_DPOP_SCHEME):
        return None
    return authorization[len(_DPOP_SCHEME) :].strip() or None


def _endpoint_uri(request: Request) -> str:
    """このサーバーが外へ名乗る、この口の URL（証明の ``htu`` と比べる。ADR-0103）。

    ⚠ ``APP_BASE_URL`` から組み立てる。前段の proxy（cloudflared・nginx）の後ろでは、要求の
    ``Host``・スキームはアプリが署名した URL と食い違う。未設定（手元の開発）のときだけ要求から作る。
    """
    base = settings.app_base_url.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}{request.url.path}"


async def get_app_or_web_principal(
    request: Request,
    credentials: BearerDep,
    gateway: AppTokenGatewayDep,
    db: DbDep,
    access_token_cookie: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
    dpop: Annotated[str | None, Header(alias="DPoP")] = None,
    id_token: Annotated[str | None, Header(alias="X-ID-Token")] = None,
) -> AuthenticatedPrincipal:
    dpop_token = _dpop_token(authorization)
    bearer = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
    app_token = dpop_token or bearer
    if app_token is None or (dpop_token is None and _is_our_token(app_token)) or not settings.app_client_ids:
        principal = await get_operation_principal(credentials, access_token_cookie)
        if principal.is_machine:
            # scope で守られていない口なので、機械のトークンはここでも断る（ADR-0087 決定 4）
            refuse_machine(principal, "app_or_web")
        refuse_during_two_factor_setup(principal)
        return principal
    presented = PresentedAppToken(
        token=app_token,
        dpop=dpop_token is not None,
        proof=dpop,
        method=request.method.upper(),
        uri=_endpoint_uri(request),
        id_token=id_token,
    )
    # ⚠ **DB と HTTP はスレッドへ逃がし、ログの文脈はここで置く。** スレッドの中で置いた ``ContextVar`` は
    #   ミドルウェアへ戻らない（ADR-0100 決定 3）。
    principal = await run_in_threadpool(_principal_of_app_token, db, gateway, presented)
    user_id_hash_var.set(principal.id_hash)
    actor_user_id_var.set(principal.user_id)
    return principal


AppOrWebPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_app_or_web_principal)]

__all__ = ["AppOrWebPrincipalDep", "app_token_gateway", "get_app_or_web_principal"]
