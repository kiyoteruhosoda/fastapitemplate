"""認証 API（ログイン・トークン更新・パスワード変更／リセット）。

認証の結果は監査ログ（``audit_log``）へも残す。失敗したログイン試行は
``result=failure`` で記録され、``reason`` に「なぜ失敗したか」の分類が入る
（パスワード・メールアドレスそのものは記録しない。ADR-0013）。

ログインの資格情報検証そのものは :class:`~presentation.fastapi.services.login_service.LoginService`
が持つ。ここは受け取った結果をトークンと Cookie に載せる HTTP の関心事だけを扱う。

ログアウトは記録しない。Cookie を落とすだけの未認証エンドポイントで、操作した
利用者を特定できないため。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

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
from presentation.fastapi.dependencies.login import LoginServiceDep
from presentation.fastapi.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    ProfileUpdateRequest,
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


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, login_service: LoginServiceDep) -> TokenResponse:
    """パスワード認証。二要素認証が有効なら ``totp_code`` も必須になる。"""
    user = login_service.authenticate(body)
    pair = TokenService.create_token_pair(user)
    set_access_token_cookie(response, str(pair["access_token"]))
    logger.info("login_succeeded")
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


@router.put("/me", response_model=MeResponse)
async def update_me(
    body: ProfileUpdateRequest,
    principal: PrincipalDep,
    db: DbDep,
    audit: AuditRecorderDep,
) -> MeResponse:
    """本人のメールアドレス・表示名を変更する（ADR-0016）。

    監査ログの ``reason`` には変更した項目名だけを入れ、値そのもの
    （メールアドレス・表示名）は記録しない（ADR-0013）。
    """
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_token"})
    taken = db.scalar(select(User).where(User.email == body.email, User.id != user.id))
    if taken is not None:
        audit.execute(AuditEventType.PROFILE_UPDATED, AuditResult.FAILURE, reason="email_already_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"})

    changed = sorted(
        name
        for name, new, old in (("email", body.email, user.email), ("username", body.username, user.username))
        if new != old
    )
    user.email = body.email
    user.username = body.username
    try:
        # 事前の SELECT は同時更新の相手が見えない（TOCTOU）。一意制約の違反を
        # ここで確定させてから成功の監査を積む（積んだ後に失敗すると、更新は
        # ロールバックされたのに監査だけ success で残ってしまう）。
        db.flush()
    except IntegrityError:
        audit.execute(AuditEventType.PROFILE_UPDATED, AuditResult.FAILURE, reason="email_already_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"}) from None
    audit.execute(AuditEventType.PROFILE_UPDATED, reason=f"fields={','.join(changed) if changed else 'none'}")
    return MeResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
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
    アカウントの持ち主を実行者に据えると本人の操作に見えてしまう（ADR-0013）。
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
