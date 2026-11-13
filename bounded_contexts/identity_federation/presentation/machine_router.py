"""Machine endpoint (``POST /api/machine/token``. ADR-0082, ADR-0087).

Exchanges a token obtained with assay ``client_credentials`` for this app's access token. From then on, machines
call **the same API as humans** with ``Authorization: Bearer``. Only scope-guarded endpoints pass, and the scope
is narrowed to the overlap of the allowlist's operations and the acting user's permissions.

⚠ **Never reads or sets cookies.** Accepting cookies would let a link clicked in a signed-in browser hit
this endpoint. Machines have no cookies, so the result is returned only in the body.
"""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from bounded_contexts.audit.application.use_cases.record_audit_event import RecordAuditEvent
from bounded_contexts.audit.domain.entities.audit_event import AuditEventType, AuditResult
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.application.use_cases.exchange_machine_token import (
    ExchangeMachineToken,
    MachineEntrance,
    MachineSession,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityFederationError,
    IdentityProviderUnavailableError,
    MachineActorNotFoundError,
    MachineClientNotRegisteredError,
)
from bounded_contexts.identity_federation.domain.services.machine_token_gateway import MachineTokenGateway
from bounded_contexts.identity_federation.domain.value_objects.machine_client import parse_machine_clients
from bounded_contexts.identity_federation.infrastructure.httpx_machine_token_gateway import (
    HttpxMachineTokenGateway,
)
from bounded_contexts.identity_federation.infrastructure.sql_machine_actors import SqlMachineActors
from presentation.fastapi.services.token_service import create_machine_access_token
from shared.infrastructure.models import User
from shared.infrastructure.tenant_directory import tenant_issuing
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/machine", tags=["machine"])

DbDep = Annotated[Session, Depends(get_db)]
#: ⚠ Read only the header (never falls back to cookies). ``auto_error=False`` is to turn "missing" into 401.
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))]

#: Code for a 401 that gives no reason. Distinguishing "endpoint closed", "not registered" and "no user to act as"
#: would let a tokenless party **probe registrations**. Diagnosis is done via our logs and audit.
MACHINE_AUTHENTICATION_REQUIRED = "machine_authentication_required"

#: Cache of discovery and JWKS. ⚠ One reused per process (creating one per request would defeat both the cache
#: and the refetch throttling)
_gateway = HttpxMachineTokenGateway()


def machine_token_gateway() -> MachineTokenGateway:
    return _gateway


MachineTokenGatewayDep = Annotated[MachineTokenGateway, Depends(machine_token_gateway)]


class MachineTokenResponse(BaseModel):
    """Exchange result. ⚠ No ``refresh_token`` is returned (machines just fetch again)."""

    access_token: str
    token_type: str
    expires_in: int
    #: Who it is acting as (for humans to check)
    acts_as: str
    client_name: str
    #: Operations actually available (overlap of the allowlist and the user's permissions)
    scopes: list[str]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": MACHINE_AUTHENTICATION_REQUIRED},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _exchange(db: Session, token: str, gateway: MachineTokenGateway) -> ExchangeMachineToken:
    """Accept in the tenant of the token's issuer (ADR-0079 §4). Reject issuers that are unregistered or whose
    tenant is suspended.

    ⚠ The issuer is read before the signature is checked, but **that value is only used to pick the key and tenant**.
    Claiming a registered issuer only passes with that issuer's signature.
    """
    tenant = tenant_issuing(db, _unverified_issuer_of(token))
    usable = tenant is not None and tenant.is_active and bool(tenant.issuer)
    return ExchangeMachineToken(
        entrance=MachineEntrance(
            audience=settings.machine_audience,
            clients=parse_machine_clients(settings.machine_clients),
        ),
        issuer=(tenant.issuer or "") if usable and tenant is not None else "",
        gateway=gateway,
        actors=SqlMachineActors(db, tenant.id if usable and tenant is not None else 0),
    )


def _unverified_issuer_of(token: str) -> str:
    try:
        issuer = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.InvalidTokenError:
        return ""
    return issuer if isinstance(issuer, str) else ""


def _refused(audit: RecordAuditEvent, error: IdentityFederationError) -> HTTPException:
    """Record the refusal reason in audit and logs, and return a 401 that gives no reason."""
    client_id = (
        error.client_id if isinstance(error, MachineClientNotRegisteredError | MachineActorNotFoundError) else None
    )
    logger.warning("machine_token_refused", extra={"reason": error.code, "client_id": client_id})
    audit.execute(
        AuditEventType.MACHINE_TOKEN_REFUSED,
        AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.MACHINE_CLIENT, client_id),
        reason=error.code,
    )
    return _unauthorized()


@router.post("/token", response_model=MachineTokenResponse)
def issue_machine_token(
    db: DbDep, audit: AuditRecorderDep, credentials: BearerDep, gateway: MachineTokenGatewayDep
) -> MachineTokenResponse:
    """Exchange a machine token for this app's access token."""
    if credentials is None:
        raise _unauthorized()
    try:
        session = _exchange(db, credentials.credentials, gateway).execute(credentials.credentials)
    except IdentityProviderUnavailableError:
        # ⚠ Don't turn "IdP unreachable" into 401 (a legitimate caller would suspect its credentials). It becomes 502
        raise
    except IdentityFederationError as error:
        raise _refused(audit, error) from error
    return _issue(db, audit, session)


def _issue(db: Session, audit: RecordAuditEvent, session: MachineSession) -> MachineTokenResponse:
    user = db.get(User, session.user_id)
    if user is None:  # pragma: no cover - already looked up in the same session
        raise _unauthorized()
    issued = create_machine_access_token(user, client_id=session.client.client_id, operations=session.client.operations)
    # "Who" is the acting user; "which machine" is kept as the target (ADR-0082 §1 decision 4)
    audit.as_actor(user.id).execute(
        AuditEventType.MACHINE_TOKEN_ISSUED,
        target=AuditTarget.of(AuditTargetType.MACHINE_CLIENT, session.client.client_id),
        reason=f"client={session.client.name}"[:255],
    )
    logger.info("machine_token_issued", extra={"client_id": session.client.client_id})
    return MachineTokenResponse(
        access_token=issued.token,
        token_type="bearer",
        expires_in=issued.expires_in,
        acts_as=session.client.acts_as,
        client_name=session.client.name,
        scopes=issued.scopes,
    )


__all__ = ["MACHINE_AUTHENTICATION_REQUIRED", "machine_token_gateway", "router"]
