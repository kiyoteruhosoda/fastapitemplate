"""パスキーによるログイン API（未認証で呼べる）。

パスワードの代わりに認証器の署名で本人確認を行う。検証に成功したら通常の
ログインと同じトークン対を発行する。
"""

from __future__ import annotations

import logging
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
from presentation.fastapi.dependencies.auth import set_access_token_cookie
from presentation.fastapi.schemas.auth import TokenResponse
from presentation.fastapi.services.token_service import TokenService
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/passkey", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/challenge", response_model=PasskeyChallengeResponse)
async def create_login_challenge(
    use_case: Annotated[StartPasskeyAuthentication, Depends(dependencies.start_passkey_authentication)],
) -> PasskeyChallengeResponse:
    """ログイン用のチャレンジを発行する（``navigator.credentials.get`` 用）。

    誰がログインするかは指定しない。認証器に登録済みの資格情報を選ばせることで、
    メールアドレスの入力なしにログインできる。
    """
    challenge = use_case.execute()
    return PasskeyChallengeResponse(challenge_id=challenge.challenge_id, public_key=challenge.public_key)


@router.post("/login", response_model=TokenResponse)
async def login_with_passkey(
    body: PasskeyAuthenticationRequest,
    response: Response,
    db: DbDep,
    use_case: Annotated[
        CompletePasskeyAuthentication,
        Depends(dependencies.complete_passkey_authentication),
    ],
) -> TokenResponse:
    user_id = use_case.execute(challenge_id=body.challenge_id, credential=body.credential)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    pair = TokenService.create_token_pair(user)
    set_access_token_cookie(response, str(pair["access_token"]))
    logger.info("passkey_login_succeeded")
    return TokenResponse(**pair)  # type: ignore[arg-type]
