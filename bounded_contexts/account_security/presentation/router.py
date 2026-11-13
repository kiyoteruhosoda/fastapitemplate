"""Account security API (a signed-in user manages their own settings).

The target is "yourself" only. Other people's accounts are not handled, so no scope is required;
being authenticated is the only condition (admin operations on someone else's two-factor
authentication belong to ``/api/admin/users``).

**Enabling and removing** two-factor authentication and passkeys is recorded in the audit log.
Increases and decreases in the means protecting an account are the first thing looked at when
investigating a security incident. Shared keys and credentials themselves are not recorded
(ADR-0075 §1). Starting enrollment (issuing a challenge) and viewing the list are not recorded
(they don't change state).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from bounded_contexts.account_security.application.dto.account_security_dto import (
    PasskeySummaryDto,
)
from bounded_contexts.account_security.application.use_cases.manage_passkeys import (
    DeletePasskey,
    ListPasskeys,
)
from bounded_contexts.account_security.application.use_cases.manage_totp import (
    ConfirmTotpEnrollment,
    DisableTotp,
    GetTwoFactorStatus,
    StartTotpEnrollment,
)
from bounded_contexts.account_security.application.use_cases.register_passkey import (
    CompletePasskeyRegistration,
    StartPasskeyRegistration,
)
from bounded_contexts.account_security.presentation import dependencies
from bounded_contexts.account_security.presentation.qr_code import (
    render_qr_code_data_uri,
)
from bounded_contexts.account_security.presentation.schemas import (
    PasskeyChallengeResponse,
    PasskeyRegistrationRequest,
    PasskeyResponse,
    TotpCodeRequest,
    TotpEnrollmentResponse,
    TwoFactorStatusResponse,
)
from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import get_settled_principal, require_recent_sign_in
from presentation.fastapi.dependencies.local_login import require_local_login
from presentation.fastapi.schemas.auth import StatusResponse
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import isoformat_utc

router = APIRouter(prefix="/api/account/security", tags=["account-security"])

#: ⚠ **Gate for routes that rework credentials** (ADR-0076 §5 decision 6). Enrolling/removing
#: two-factor authentication or passkeys "creates a new way in", so **check the current state before
#: letting it through** — a suspended user's access token in hand still works until it expires.
PrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_settled_principal)]


def _to_passkey_response(summary: PasskeySummaryDto) -> PasskeyResponse:
    return PasskeyResponse(
        id=summary.id,
        name=summary.name,
        transports=list(summary.transports),
        created_at=isoformat_utc(summary.created_at) if summary.created_at else None,
        last_used_at=isoformat_utc(summary.last_used_at) if summary.last_used_at else None,
    )


# ---------------------------------------------------------------------------
# Two-factor authentication (TOTP)
# ---------------------------------------------------------------------------


@router.get("/two-factor", response_model=TwoFactorStatusResponse)
def two_factor_status(
    principal: PrincipalDep,
    use_case: Annotated[GetTwoFactorStatus, Depends(dependencies.get_two_factor_status)],
) -> TwoFactorStatusResponse:
    status_dto = use_case.execute(principal.user_id)
    return TwoFactorStatusResponse(
        enabled=status_dto.enabled,
        enrolling=status_dto.enrolling,
        required=settings.local_two_factor_required,
    )


@router.post(
    "/two-factor/enrollment", response_model=TotpEnrollmentResponse, dependencies=[Depends(require_local_login)]
)
def start_two_factor_enrollment(
    principal: PrincipalDep,
    use_case: Annotated[StartTotpEnrollment, Depends(dependencies.start_totp_enrollment)],
) -> TotpEnrollmentResponse:
    """Issue a shared key. Two-factor authentication is not enabled yet at this point."""
    enrollment = use_case.execute(user_id=principal.user_id, account_name=principal.email)
    return TotpEnrollmentResponse(
        secret=enrollment.secret,
        otpauth_uri=enrollment.otpauth_uri,
        qr_code=render_qr_code_data_uri(enrollment.otpauth_uri),
    )


@router.post("/two-factor/confirmation", response_model=StatusResponse, dependencies=[Depends(require_local_login)])
def confirm_two_factor_enrollment(
    body: TotpCodeRequest,
    principal: PrincipalDep,
    use_case: Annotated[ConfirmTotpEnrollment, Depends(dependencies.confirm_totp_enrollment)],
    audit: AuditRecorderDep,
) -> StatusResponse:
    """Verify the authenticator app's code and enable two-factor authentication."""
    use_case.execute(user_id=principal.user_id, code=body.code)
    audit.execute(
        AuditEventType.TWO_FACTOR_ENABLED,
        target=AuditTarget.of(AuditTargetType.TWO_FACTOR, principal.user_id),
    )
    return StatusResponse(status="ok")


@router.post("/two-factor/removal", response_model=StatusResponse)
def disable_two_factor(
    body: TotpCodeRequest,
    principal: PrincipalDep,
    use_case: Annotated[DisableTotp, Depends(dependencies.disable_totp)],
    audit: AuditRecorderDep,
) -> StatusResponse:
    if settings.local_two_factor_required:
        # If it could be removed, it would just mean re-enrolling at every login; no protection (ADR-0093)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "two_factor_required"})
    use_case.execute(user_id=principal.user_id, code=body.code)
    audit.execute(
        AuditEventType.TWO_FACTOR_DISABLED,
        target=AuditTarget.of(AuditTargetType.TWO_FACTOR, principal.user_id),
    )
    return StatusResponse(status="ok")


# ---------------------------------------------------------------------------
# Passkeys (WebAuthn)
# ---------------------------------------------------------------------------


@router.get("/passkeys", response_model=list[PasskeyResponse])
def list_registered_passkeys(
    principal: PrincipalDep,
    use_case: Annotated[ListPasskeys, Depends(dependencies.list_passkeys)],
) -> list[PasskeyResponse]:
    return [_to_passkey_response(item) for item in use_case.execute(principal.user_id)]


@router.post(
    "/passkeys/registration",
    response_model=PasskeyChallengeResponse,
    # Adds a way in. Only right after re-authenticating (ADR-0076 §10)
    dependencies=[Depends(require_local_login), Depends(require_recent_sign_in)],
)
def start_passkey_registration(
    principal: PrincipalDep,
    use_case: Annotated[StartPasskeyRegistration, Depends(dependencies.start_passkey_registration)],
) -> PasskeyChallengeResponse:
    """Issue a registration challenge (for ``navigator.credentials.create``)."""
    challenge = use_case.execute(
        user_id=principal.user_id,
        user_name=principal.email,
        display_name=principal.username,
    )
    return PasskeyChallengeResponse(challenge_id=challenge.challenge_id, public_key=challenge.public_key)


@router.post(
    "/passkeys",
    response_model=PasskeyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recent_sign_in)],
)
def complete_passkey_registration(
    body: PasskeyRegistrationRequest,
    principal: PrincipalDep,
    use_case: Annotated[CompletePasskeyRegistration, Depends(dependencies.complete_passkey_registration)],
    audit: AuditRecorderDep,
) -> PasskeyResponse:
    summary = use_case.execute(
        user_id=principal.user_id,
        challenge_id=body.challenge_id,
        credential=body.credential,
        name=body.name,
    )
    audit.execute(
        AuditEventType.PASSKEY_REGISTERED,
        target=AuditTarget.of(AuditTargetType.PASSKEY, summary.id),
    )
    return _to_passkey_response(summary)


@router.delete(
    "/passkeys/{passkey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Deleting one's own passkeys can lock one out too, so only right after re-authenticating (ADR-0076 §10)
    dependencies=[Depends(require_recent_sign_in)],
)
def delete_registered_passkey(
    passkey_id: int,
    principal: PrincipalDep,
    use_case: Annotated[DeletePasskey, Depends(dependencies.delete_passkey)],
    audit: AuditRecorderDep,
) -> None:
    use_case.execute(user_id=principal.user_id, passkey_id=passkey_id)
    audit.execute(
        AuditEventType.PASSKEY_DELETED,
        target=AuditTarget.of(AuditTargetType.PASSKEY, passkey_id),
    )
