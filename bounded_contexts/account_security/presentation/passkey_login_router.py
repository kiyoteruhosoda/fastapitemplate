"""パスキーによるログイン API（未認証で呼べる）。

パスワードの代わりに認証器の署名で本人確認を行う。検証に成功したら通常の
ログインと同じトークン対を発行する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from bounded_contexts.account_security.application.use_cases.authenticate_with_passkey import (
    CompletePasskeyAuthentication,
    StartPasskeyAuthentication,
)
from bounded_contexts.account_security.presentation import dependencies
from bounded_contexts.account_security.presentation.schemas import (
    PasskeyAuthenticationRequest,
    PasskeyChallengeResponse,
)
from bounded_contexts.audit.application.use_cases.record_audit_event import RecordAuditEvent
from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.local_login import require_local_login
from presentation.fastapi.schemas.auth import SessionResponse
from presentation.fastapi.services.session_cookies import establish_session
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/passkey", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class _LoginRecording:
    """ログインの成立を記録するのに要るもの（DB と監査）。

    束ねているのは、ルーターの引数を設計上の数（4 個）に収めるため。どちらも
    ``Depends()`` の注入で、業務上の入力ではない。
    """

    db: Session
    audit: RecordAuditEvent


def login_recording(db: DbDep, audit: AuditRecorderDep) -> _LoginRecording:
    return _LoginRecording(db=db, audit=audit)


@router.post("/challenge", response_model=PasskeyChallengeResponse, dependencies=[Depends(require_local_login)])
async def create_login_challenge(
    use_case: Annotated[StartPasskeyAuthentication, Depends(dependencies.start_passkey_authentication)],
) -> PasskeyChallengeResponse:
    """ログイン用のチャレンジを発行する（``navigator.credentials.get`` 用）。

    誰がログインするかは指定しない。認証器に登録済みの資格情報を選ばせることで、
    メールアドレスの入力なしにログインできる。
    """
    challenge = use_case.execute()
    return PasskeyChallengeResponse(challenge_id=challenge.challenge_id, public_key=challenge.public_key)


@router.post("/login", response_model=SessionResponse, dependencies=[Depends(require_local_login)])
async def login_with_passkey(
    body: PasskeyAuthenticationRequest,
    response: Response,
    recording: Annotated[_LoginRecording, Depends(login_recording)],
    use_case: Annotated[
        CompletePasskeyAuthentication,
        Depends(dependencies.complete_passkey_authentication),
    ],
) -> SessionResponse:
    user_id = use_case.execute(challenge_id=body.challenge_id, credential=body.credential)

    user = recording.db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    session = establish_session(response, user)
    # どの入口で入ったかを残す（ADR-0026 決定 1）。
    recording.audit.as_actor(user.id).execute(AuditEventType.LOGIN_SUCCEEDED, reason="method=passkey")
    logger.info("passkey_login_succeeded")
    return session
