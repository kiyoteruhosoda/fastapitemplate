"""JWT の発行・検証（access / refresh の2トークン）。

- scope クレームはユーザーの保有権限の範囲内。未指定・空 = 権限なし。
- ``active_role`` クレームは「いまどのロールで操作しているか」（ADR-0017）。
  ``None`` は「すべてのロール」＝保有権限の和集合。指定されている場合、scope は
  そのロール 1 つ分の権限に絞られる。切り替えは新しいトークンの発行で行う。
- 検証結果は ``AuthenticatedPrincipal`` として返す。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings

_ALGORITHM = "HS256"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
# アクティブロール名を載せるクレーム名（access / refresh の双方に入れる。
# refresh に無いと、トークン更新のたびに「すべてのロール」へ戻ってしまう）
CLAIM_ACTIVE_ROLE = "active_role"


class TokenService:
    @staticmethod
    def create_token_pair(
        user: User,
        *,
        scopes: list[str] | None = None,
        active_role: str | None = None,
    ) -> dict[str, object]:
        """access / refresh トークンを発行する。

        ``scopes`` を指定した場合もアクティブロールの権限との積集合に切り詰める。
        """
        granted = user.permission_codes_of(active_role)
        effective = sorted(granted if scopes is None else granted & set(scopes))
        now = datetime.now(UTC)
        base_claims = {
            "sub": str(user.id),
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "iat": now,
            CLAIM_ACTIVE_ROLE: active_role,
        }
        access = jwt.encode(
            {
                **base_claims,
                "type": TYPE_ACCESS,
                "scope": effective,
                "email": user.email,
                "exp": now + timedelta(seconds=settings.access_token_expires_seconds),
            },
            settings.jwt_secret_key,
            algorithm=_ALGORITHM,
        )
        refresh = jwt.encode(
            {
                **base_claims,
                "type": TYPE_REFRESH,
                "exp": now + timedelta(seconds=settings.refresh_token_expires_seconds),
            },
            settings.jwt_secret_key,
            algorithm=_ALGORITHM,
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": settings.access_token_expires_seconds,
        }

    @staticmethod
    def _decode(token: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            claims = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[_ALGORITHM],
                audience=settings.access_token_audience,
                issuer=settings.access_token_issuer,
            )
            return claims, None
        except jwt.ExpiredSignatureError:
            return None, "token_expired"
        except jwt.InvalidTokenError:
            return None, "token_invalid"

    @classmethod
    def verify_access_token_with_reason(
        cls, token: str, *, session: Session
    ) -> tuple[AuthenticatedPrincipal | None, str | None]:
        claims, reason = cls._decode(token)
        if claims is None:
            return None, reason
        if claims.get("type") != TYPE_ACCESS:
            return None, "not_access_token"
        user = cls._load_active_user(claims, session)
        if user is None:
            return None, "user_not_found_or_inactive"
        # scope はアクティブロールの現在の権限との積集合（失効した権限、および
        # 切り替えた後に外されたロールの権限を無効化する）
        active_role = _active_role_of(claims)
        scope = frozenset(claims.get("scope") or ()) & user.permission_codes_of(active_role)
        return (
            AuthenticatedPrincipal(
                user_id=user.id,
                email=user.email,
                username=user.username,
                permissions=scope,
                active_role=active_role,
            ),
            None,
        )

    @classmethod
    def verify_refresh_token(cls, token: str, *, session: Session) -> tuple[User, str | None] | None:
        """更新対象のユーザーと、そのセッションのアクティブロールを返す。"""
        claims, _ = cls._decode(token)
        if claims is None or claims.get("type") != TYPE_REFRESH:
            return None
        user = cls._load_active_user(claims, session)
        if user is None:
            return None
        return user, _active_role_of(claims)

    @staticmethod
    def _load_active_user(claims: dict[str, Any], session: Session) -> User | None:
        try:
            user_id = int(claims.get("sub", ""))
        except ValueError:
            return None
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user


def _active_role_of(claims: dict[str, Any]) -> str | None:
    """クレームのアクティブロール。無い・文字列でないものは「すべてのロール」扱い。

    クレームを持たない発行済みトークン（この機能より前のもの）もそのまま使える。
    """
    value = claims.get(CLAIM_ACTIVE_ROLE)
    return value if isinstance(value, str) else None


__all__ = ["CLAIM_ACTIVE_ROLE", "TYPE_ACCESS", "TYPE_REFRESH", "TokenService"]
