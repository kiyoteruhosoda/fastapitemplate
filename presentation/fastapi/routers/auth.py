"""認証 API（ログイン・トークン更新・パスワード変更／リセット）。

認証の結果は監査ログ（``audit_log``）へも残す。失敗したログイン試行は
``result=failure`` で記録され、``reason`` に「なぜ失敗したか」の分類が入る
（パスワード・メールアドレスそのものは記録しない。ADR-0008）。

ログアウトは記録しない。Cookie を落とすだけの未認証エンドポイントで、操作した
利用者を特定できないため。
"""

from __future__ import annotations

import logging
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TotpRequiredError,
)
from bounded_contexts.account_security.presentation import dependencies as security
from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import (
    clear_access_token_cookie,
    get_current_principal,
    set_access_token_cookie,
)
from presentation.fastapi.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    ResetPasswordRequest,
    StatusResponse,
    TokenResponse,
)
from presentation.fastapi.services.password_reset_service import PasswordResetService
from presentation.fastapi.services.token_service import TokenService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

DbDep = Annotated[Session, Depends(get_db)]
PrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
SecondFactorDep = Annotated[VerifySecondFactor, Depends(security.verify_second_factor)]


def _reject_login(audit: RecordAuditEvent, user: User | None, reason: str) -> NoReturn:
    """ログイン失敗を監査ログへ残し、401 を返す。

    *reason* は失敗の分類（``unknown_email`` / ``invalid_password`` 等）。応答は
    どの理由でも同じ ``invalid_credentials`` に揃える（アカウントの存在を
    漏らさないため）。分類が分かるのは監査ログを読める管理者だけ。

    相手のアカウントは**実行者ではなく対象**として記録する。認証に失敗した時点で
    「誰が試したか」は分かっておらず、実行者に据えるとアカウントの持ち主が自分で
    やったように読めてしまう（ADR-0008）。
    """
    audit.execute(
        AuditEventType.LOGIN_FAILED,
        AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.USER, user.id) if user is not None else None,
        reason=reason,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "invalid_credentials"},
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: DbDep,
    second_factor: SecondFactorDep,
    audit: AuditRecorderDep,
) -> TokenResponse:
    """パスワード認証。二要素認証が有効なら ``totp_code`` も必須になる。

    コード未提示は ``totp_required``、不一致は ``invalid_totp`` を返す。どちらも
    パスワードは正しかったことを意味するが、この時点ではまだトークンを発行して
    いないため、コードを添えて再度ログインすればよい。
    """
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        _reject_login(audit, None, "unknown_email")
    if not user.is_active:
        _reject_login(audit, user, "inactive_user")
    if not check_password_hash(user.password_hash, body.password):
        _reject_login(audit, user, "invalid_password")

    try:
        second_factor.execute(user_id=user.id, code=body.totp_code)
    except (TotpRequiredError, InvalidTotpCodeError) as error:
        audit.execute(
            AuditEventType.LOGIN_FAILED,
            AuditResult.FAILURE,
            target=AuditTarget.of(AuditTargetType.USER, user.id),
            reason=error.code,
        )
        # 認証の失敗として 401 に揃える（既定の対応付けでは 400 になる）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": error.code},
        ) from None

    pair = TokenService.create_token_pair(user)
    set_access_token_cookie(response, str(pair["access_token"]))
    logger.info("login_succeeded")
    audit.execute(AuditEventType.LOGIN_SUCCEEDED, actor_user_id=user.id)
    return TokenResponse(**pair)  # type: ignore[arg-type]


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, response: Response, db: DbDep) -> TokenResponse:
    user = TokenService.verify_refresh_token(body.refresh_token, session=db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    pair = TokenService.create_token_pair(user)
    set_access_token_cookie(response, str(pair["access_token"]))
    return TokenResponse(**pair)  # type: ignore[arg-type]


@router.post("/logout", response_model=StatusResponse)
async def logout(response: Response) -> StatusResponse:
    clear_access_token_cookie(response)
    return StatusResponse(status="ok")


@router.get("/me", response_model=MeResponse)
async def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        email=principal.email,
        username=principal.username,
        scopes=sorted(principal.permissions),
    )


@router.post("/change-password", response_model=StatusResponse)
async def change_password(
    body: ChangePasswordRequest,
    principal: PrincipalDep,
    db: DbDep,
    audit: AuditRecorderDep,
) -> StatusResponse:
    user = db.get(User, principal.user_id)
    if user is None or not check_password_hash(user.password_hash, body.current_password):
        audit.execute(
            AuditEventType.PASSWORD_CHANGED,
            AuditResult.FAILURE,
            reason="invalid_current_password",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_current_password"},
        )
    user.password_hash = generate_password_hash(body.new_password)
    logger.info("password_changed")
    audit.execute(AuditEventType.PASSWORD_CHANGED)
    return StatusResponse(status="ok")


@router.post("/forgot-password", response_model=StatusResponse)
async def forgot_password(body: ForgotPasswordRequest, db: DbDep, audit: AuditRecorderDep) -> StatusResponse:
    """再設定リンクを送る。

    未認証のエンドポイントなので、監査ログでは要求されたアカウントを**対象**として
    記録し、実行者は空のままにする。メールアドレスを知っていれば誰でも叩けるため、
    アカウントの持ち主を実行者に据えると本人の操作に見えてしまう（ADR-0008）。
    """
    # ユーザーの存在有無に関わらず同じ応答を返す（列挙攻撃対策）
    user_id = PasswordResetService().request_reset(db, body.email)
    audit.execute(
        AuditEventType.PASSWORD_RESET_REQUESTED,
        AuditResult.SUCCESS if user_id is not None else AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.USER, user_id) if user_id is not None else None,
        reason=None if user_id is not None else "unknown_email",
    )
    return StatusResponse(status="accepted")


@router.post("/reset-password", response_model=StatusResponse)
async def reset_password(body: ResetPasswordRequest, db: DbDep, audit: AuditRecorderDep) -> StatusResponse:
    """トークンで新しいパスワードを設定する。

    こちらも未認証（トークンの提示だけ）なので、対象として記録し実行者は空にする。
    """
    user_id = PasswordResetService().reset(db, body.token, body.new_password)
    if user_id is None:
        audit.execute(
            AuditEventType.PASSWORD_RESET_COMPLETED,
            AuditResult.FAILURE,
            reason="invalid_or_expired_token",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    audit.execute(
        AuditEventType.PASSWORD_RESET_COMPLETED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
    )
    return StatusResponse(status="ok")
