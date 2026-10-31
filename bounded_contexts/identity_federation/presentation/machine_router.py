"""機械の口（``POST /api/machine/token``。ADR-0082・ADR-0087）。

assay の ``client_credentials`` で得たトークンを、このアプリのアクセストークンへ換える。以降、機械は
**人と同じ API** を ``Authorization: Bearer`` で叩く。通るのは scope で守られた口だけで、scope は
許可簿の操作と、振る舞う利用者の権限の重なりに絞ってある。

⚠ **Cookie を読まない・載せない。** Cookie を受け付けると、ログイン中のブラウザが踏んだリンクから
この口を叩けることになる。機械は Cookie を持たないので、本文で返すだけにする。
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
#: ⚠ ヘッダーだけ読む（Cookie へ落ちない）。``auto_error=False`` は「無い」を 401 にするため。
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))]

#: 理由を言わない 401 のコード。「口が閉じている」「登録が無い」「振る舞う相手が居ない」を区別して返すと、
#: トークンを持たない相手が**登録の有無を探れる**。切り分けはこちらのログと監査で行う。
MACHINE_AUTHENTICATION_REQUIRED = "machine_authentication_required"

#: discovery と JWKS の控え。⚠ プロセスで 1 つを使い回す（要求ごとに作ると控えも取り直しの抑えも効かない）
_gateway = HttpxMachineTokenGateway()


def machine_token_gateway() -> MachineTokenGateway:
    return _gateway


MachineTokenGatewayDep = Annotated[MachineTokenGateway, Depends(machine_token_gateway)]


class MachineTokenResponse(BaseModel):
    """換えた結果。⚠ ``refresh_token`` は返さない（機械は取り直せばよい）。"""

    access_token: str
    token_type: str
    expires_in: int
    #: 誰として振る舞っているか（人が確かめるため）
    acts_as: str
    client_name: str
    #: 実際に使える操作（許可簿と利用者の権限の重なり）
    scopes: list[str]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": MACHINE_AUTHENTICATION_REQUIRED},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _exchange(db: Session, token: str, gateway: MachineTokenGateway) -> ExchangeMachineToken:
    """トークンの発行者のテナントで受ける（ADR-0079 §4）。登録の無い・止めたテナントの発行者は受けない。

    ⚠ 発行者は署名を確かめる前に読むが、**その値は鍵とテナントを選ぶのにしか使わない**。登録のある発行者を
    名乗っても、署名はその発行者の鍵でしか通らない。
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
    """断った理由を監査とログに残し、理由を言わない 401 を返す。"""
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
    """機械のトークンを、このアプリのアクセストークンへ換える。"""
    if credentials is None:
        raise _unauthorized()
    try:
        session = _exchange(db, credentials.credentials, gateway).execute(credentials.credentials)
    except IdentityProviderUnavailableError:
        # ⚠ IdP と話せないことを 401 にしない（正しい呼び出し元が資格情報を疑う）。502 になる
        raise
    except IdentityFederationError as error:
        raise _refused(audit, error) from error
    return _issue(db, audit, session)


def _issue(db: Session, audit: RecordAuditEvent, session: MachineSession) -> MachineTokenResponse:
    user = db.get(User, session.user_id)
    if user is None:  # pragma: no cover - 同じセッションで引けている
        raise _unauthorized()
    issued = create_machine_access_token(user, client_id=session.client.client_id, operations=session.client.operations)
    # 「誰が」は振る舞う利用者、「どの機械が」は対象に残す（ADR-0082 §1 決定 4）
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
