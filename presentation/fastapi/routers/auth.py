"""認証 API（ログイン・トークン更新・パスワード変更／リセット）。"""

from __future__ import annotations

import logging
from typing import Annotated

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


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: DbDep,
    second_factor: SecondFactorDep,
) -> TokenResponse:
    """パスワード認証。二要素認証が有効なら ``totp_code`` も必須になる。

    コード未提示は ``totp_required``、不一致は ``invalid_totp`` を返す。どちらも
    パスワードは正しかったことを意味するが、この時点ではまだトークンを発行して
    いないため、コードを添えて再度ログインすればよい。
    """
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not user.is_active or not check_password_hash(user.password_hash, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    try:
        second_factor.execute(user_id=user.id, code=body.totp_code)
    except (TotpRequiredError, InvalidTotpCodeError) as error:
        # 認証の失敗として 401 に揃える（既定の対応付けでは 400 になる）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": error.code},
        ) from None

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


@router.post("/change-password", response_model=StatusResponse)
async def change_password(body: ChangePasswordRequest, principal: PrincipalDep, db: DbDep) -> StatusResponse:
    user = db.get(User, principal.user_id)
    if user is None or not check_password_hash(user.password_hash, body.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_current_password"},
        )
    user.password_hash = generate_password_hash(body.new_password)
    logger.info("password_changed")
    return StatusResponse(status="ok")


@router.post("/forgot-password", response_model=StatusResponse)
async def forgot_password(body: ForgotPasswordRequest, db: DbDep) -> StatusResponse:
    # ユーザーの存在有無に関わらず同じ応答を返す（列挙攻撃対策）
    PasswordResetService().request_reset(db, body.email)
    return StatusResponse(status="accepted")


@router.post("/reset-password", response_model=StatusResponse)
async def reset_password(body: ResetPasswordRequest, db: DbDep) -> StatusResponse:
    if not PasswordResetService().reset(db, body.token, body.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    return StatusResponse(status="ok")
