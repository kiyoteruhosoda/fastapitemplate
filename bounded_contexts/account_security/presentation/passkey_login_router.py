"""Passkey login API (callable unauthenticated).

Verifies identity with the authenticator's signature instead of a password. On successful
verification, issues the same token pair as a normal login.
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
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from presentation.fastapi.services.session_cookies import establish_session
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/passkey", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class _LoginRecording:
    """What is needed to record a successful login (DB and audit).

    Bundled to keep the router's arguments within the designed count (4). Both are injected via
    ``Depends()`` and are not business inputs.
    """

    db: Session
    audit: RecordAuditEvent


def login_recording(db: DbDep, audit: AuditRecorderDep) -> _LoginRecording:
    return _LoginRecording(db=db, audit=audit)


@router.post("/challenge", response_model=PasskeyChallengeResponse, dependencies=[Depends(require_local_login)])
def create_login_challenge(
    use_case: Annotated[StartPasskeyAuthentication, Depends(dependencies.start_passkey_authentication)],
) -> PasskeyChallengeResponse:
    """Issue a login challenge (for ``navigator.credentials.get``).

    Who is logging in is not specified. Letting the authenticator pick a registered credential
    allows login without entering an email address.
    """
    challenge = use_case.execute()
    return PasskeyChallengeResponse(challenge_id=challenge.challenge_id, public_key=challenge.public_key)


@router.post("/login", response_model=SessionResponse, dependencies=[Depends(require_local_login)])
def login_with_passkey(
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

    session = establish_session(response, user, SessionCarryOver(signed_in_with_passkey=True))
    # Record which entry point was used (ADR-0076 §3 decision 1).
    recording.audit.as_actor(user.id).execute(AuditEventType.LOGIN_SUCCEEDED, reason="method=passkey")
    logger.info("passkey_login_succeeded")
    return session
