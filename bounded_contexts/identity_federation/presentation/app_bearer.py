"""Gate for calls from apps (Android apps signed in directly to assay) (ADR-0081 §1).

⚠ **App tokens only pass on routers that use this dependency** (ones declared "callable from
apps"). Admin, account and token reissue endpoints still use
:func:`presentation.fastapi.dependencies.auth.get_current_principal` (this app's tokens only).
⚠ **If ``APP_CLIENT_IDS`` is empty, no assay token is accepted at all** (behaves the same as 1).

In order:

1. A token issued by this app (web cookie / header) passes as is
2. An assay access token sent as ``Authorization: Bearer`` is checked for acceptance and
   resolved to a user
   — permissions are looked up **from the DB every time** (they are not in assay tokens)
3. ``Authorization: DPoP`` is checked together with the proof in the ``DPoP`` header (ADR-0103).
   Tokens with ``cnf.jkt`` (bound to a device key) only pass this way
4. Otherwise, the same 401 as 1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
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
#: ``Authorization: DPoP <token>`` (RFC 9449 §7.1). ``HTTPBearer`` only reads ``Bearer``,
#: so we read it ourselves.
_DPOP_SCHEME = "dpop "


def app_token_gateway() -> AppTokenGateway:
    return _app_token_gateway


AppTokenGatewayDep = Annotated[AppTokenGateway, Depends(app_token_gateway)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def authenticate_app_access_token(db: Session, gateway: AppTokenGateway, token: str) -> AuthenticateAppAccessToken:
    """Accept in the tenant of the token's issuer (ADR-0079 §4). Reject unregistered issuers.

    ⚠ The issuer is read before the signature is checked, but **that value is only used to pick
    the key**. Claiming a registered issuer only passes with that issuer's signature.
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
    """Token from ``Authorization: DPoP <token>``. ``None`` if the scheme is not ``DPoP``."""
    if authorization is None or not authorization.lower().startswith(_DPOP_SCHEME):
        return None
    return authorization[len(_DPOP_SCHEME) :].strip() or None


def _endpoint_uri(request: Request) -> str:
    """This endpoint's URL as this server presents it externally (compared with the proof's ``htu``.
    ADR-0103).

    ⚠ Built from ``APP_BASE_URL``. Behind the front proxy (cloudflared, nginx) the request's
    ``Host`` and scheme differ from the URL the app signed. Only built from the request when
    unset (local development).
    """
    base = settings.app_base_url.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}{request.url.path}"


@dataclass(frozen=True)
class _AppRequest:
    """Auth-relevant parts of a request to the app-facing endpoints (headers and target)."""

    credentials: HTTPAuthorizationCredentials | None
    #: Token from ``Authorization: DPoP <token>`` (``None`` for ``Bearer``).
    dpop_token: str | None
    proof: str | None
    id_token: str | None
    method: str
    uri: str

    @property
    def app_token(self) -> str | None:
        credentials = self.credentials
        bearer = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
        return self.dpop_token or bearer

    def presented(self, token: str) -> PresentedAppToken:
        return PresentedAppToken(
            token=token,
            dpop=self.dpop_token is not None,
            proof=self.proof,
            method=self.method,
            uri=self.uri,
            id_token=self.id_token,
        )


def _app_request(request: Request, credentials: BearerDep) -> _AppRequest:
    """Read ``Authorization`` (``Bearer`` / ``DPoP``), ``DPoP``, ``X-ID-Token`` and the target
    (ADR-0103)."""
    headers = request.headers
    return _AppRequest(
        credentials=credentials,
        dpop_token=_dpop_token(headers.get("authorization")),
        proof=headers.get("dpop"),
        id_token=headers.get("x-id-token"),
        method=request.method.upper(),
        uri=_endpoint_uri(request),
    )


async def get_app_or_web_principal(
    app_request: Annotated[_AppRequest, Depends(_app_request)],
    gateway: AppTokenGatewayDep,
    db: DbDep,
    access_token_cookie: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> AuthenticatedPrincipal:
    app_token = app_request.app_token
    is_ours = app_request.dpop_token is None and app_token is not None and _is_our_token(app_token)
    if app_token is None or is_ours or not settings.app_client_ids:
        principal = await get_operation_principal(app_request.credentials, access_token_cookie)
        if principal.is_machine:
            # Not a scope-guarded endpoint, so machine tokens are refused here too (ADR-0087 decision 4)
            refuse_machine(principal, "app_or_web")
        refuse_during_two_factor_setup(principal)
        return principal
    # ⚠ **Offload DB and HTTP to a thread and set the log context here.** A ``ContextVar`` set
    #   inside the thread does not propagate back to the middleware (ADR-0100 decision 3).
    principal = await run_in_threadpool(_principal_of_app_token, db, gateway, app_request.presented(app_token))
    user_id_hash_var.set(principal.id_hash)
    actor_user_id_var.set(principal.user_id)
    return principal


AppOrWebPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_app_or_web_principal)]

__all__ = ["AppOrWebPrincipalDep", "app_token_gateway", "get_app_or_web_principal"]
