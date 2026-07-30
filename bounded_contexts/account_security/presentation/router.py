"""アカウントセキュリティ API（ログイン中の利用者が自分の設定を操作する）。

対象は「自分自身」のみ。他人のアカウントは扱わないため scope は要求せず、
認証済みであることだけを条件にする（他人の二要素認証を触る管理操作は
``/api/admin/users`` 側の責務）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

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
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.auth import StatusResponse
from shared.application.authenticated_principal import AuthenticatedPrincipal

router = APIRouter(prefix="/api/account/security", tags=["account-security"])

PrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def _to_passkey_response(summary: PasskeySummaryDto) -> PasskeyResponse:
    return PasskeyResponse(
        id=summary.id,
        name=summary.name,
        transports=list(summary.transports),
        created_at=summary.created_at.isoformat() if summary.created_at else None,
        last_used_at=summary.last_used_at.isoformat() if summary.last_used_at else None,
    )


# ---------------------------------------------------------------------------
# 二要素認証（TOTP）
# ---------------------------------------------------------------------------


@router.get("/two-factor", response_model=TwoFactorStatusResponse)
async def two_factor_status(
    principal: PrincipalDep,
    use_case: Annotated[GetTwoFactorStatus, Depends(dependencies.get_two_factor_status)],
) -> TwoFactorStatusResponse:
    status_dto = use_case.execute(principal.user_id)
    return TwoFactorStatusResponse(enabled=status_dto.enabled, enrolling=status_dto.enrolling)


@router.post("/two-factor/enrollment", response_model=TotpEnrollmentResponse)
async def start_two_factor_enrollment(
    principal: PrincipalDep,
    use_case: Annotated[StartTotpEnrollment, Depends(dependencies.start_totp_enrollment)],
) -> TotpEnrollmentResponse:
    """共有鍵を発行する。この時点ではまだ二要素認証は有効にならない。"""
    enrollment = use_case.execute(user_id=principal.user_id, account_name=principal.email)
    return TotpEnrollmentResponse(
        secret=enrollment.secret,
        otpauth_uri=enrollment.otpauth_uri,
        qr_code=render_qr_code_data_uri(enrollment.otpauth_uri),
    )


@router.post("/two-factor/confirmation", response_model=StatusResponse)
async def confirm_two_factor_enrollment(
    body: TotpCodeRequest,
    principal: PrincipalDep,
    use_case: Annotated[ConfirmTotpEnrollment, Depends(dependencies.confirm_totp_enrollment)],
) -> StatusResponse:
    """認証アプリのコードを検証し、二要素認証を有効にする。"""
    use_case.execute(user_id=principal.user_id, code=body.code)
    return StatusResponse(status="ok")


@router.post("/two-factor/removal", response_model=StatusResponse)
async def disable_two_factor(
    body: TotpCodeRequest,
    principal: PrincipalDep,
    use_case: Annotated[DisableTotp, Depends(dependencies.disable_totp)],
) -> StatusResponse:
    use_case.execute(user_id=principal.user_id, code=body.code)
    return StatusResponse(status="ok")


# ---------------------------------------------------------------------------
# パスキー（WebAuthn）
# ---------------------------------------------------------------------------


@router.get("/passkeys", response_model=list[PasskeyResponse])
async def list_registered_passkeys(
    principal: PrincipalDep,
    use_case: Annotated[ListPasskeys, Depends(dependencies.list_passkeys)],
) -> list[PasskeyResponse]:
    return [_to_passkey_response(item) for item in use_case.execute(principal.user_id)]


@router.post("/passkeys/registration", response_model=PasskeyChallengeResponse)
async def start_passkey_registration(
    principal: PrincipalDep,
    use_case: Annotated[StartPasskeyRegistration, Depends(dependencies.start_passkey_registration)],
) -> PasskeyChallengeResponse:
    """登録用のチャレンジを発行する（``navigator.credentials.create`` 用）。"""
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
)
async def complete_passkey_registration(
    body: PasskeyRegistrationRequest,
    principal: PrincipalDep,
    use_case: Annotated[CompletePasskeyRegistration, Depends(dependencies.complete_passkey_registration)],
) -> PasskeyResponse:
    summary = use_case.execute(
        user_id=principal.user_id,
        challenge_id=body.challenge_id,
        credential=body.credential,
        name=body.name,
    )
    return _to_passkey_response(summary)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registered_passkey(
    passkey_id: int,
    principal: PrincipalDep,
    use_case: Annotated[DeletePasskey, Depends(dependencies.delete_passkey)],
) -> None:
    use_case.execute(user_id=principal.user_id, passkey_id=passkey_id)
