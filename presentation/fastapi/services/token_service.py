"""JWT の発行・検証（access / refresh の2トークン）。

- scope クレームはユーザーの保有権限の範囲内。未指定・空 = 権限なし。
- ``active_role`` クレームは「いまどのロールで操作しているか」（ADR-0017）。
  ``None`` は「すべてのロール」＝保有権限の和集合。指定されている場合、scope は
  そのロール 1 つ分の権限に絞られる。切り替えは新しいトークンの発行で行う。
- ``fed_iss`` / ``fed_sub`` / ``sid`` / ``fed_iat`` は、IdP 経由で始まったセッションの
  宛名と**始まった時刻**（ADR-0036）。**検証のたびに「止められていないか」を照合
  する**——サーバーにセッションの控えが無いので、届いた停止はここでしか効かせ
  られない。ローカルのログインで発行したトークンには載らない。
- 検証結果は ``AuthenticatedPrincipal`` として返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.application.use_cases.check_session_revocation import (
    CheckSessionRevocation,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings

_ALGORITHM = "HS256"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
# アクティブロール名を載せるクレーム名（access / refresh の双方に入れる。
# refresh に無いと、トークン更新のたびに「すべてのロール」へ戻ってしまう）
CLAIM_ACTIVE_ROLE = "active_role"
# IdP 側のセッションの宛名（ADR-0036）。``sid`` だけ OIDC と同じ綴りにする
# （ID トークンから写した値であることを読み取れるようにするため）。
CLAIM_FEDERATED_ISSUER = "fed_iss"
CLAIM_FEDERATED_SUBJECT = "fed_sub"
CLAIM_SESSION_ID = "sid"
# セッションが始まった時刻（エポックからのマイクロ秒）。``iat`` は秒までしか持たず、
# 止めた直後の同じ秒に入り直した利用者を巻き添えにするため、別に持つ。
CLAIM_FEDERATED_ISSUED_AT = "fed_iat"


@dataclass(frozen=True)
class RefreshedSession:
    """更新の対象。**入り口（``federated_session``）も一緒に返す**（ADR-0036）。

    落とすと、更新のたびに IdP のセッションの宛名が消え、**トークンを 1 回更新する
    だけで停止の伝播をすり抜けられる**。
    """

    user: User
    active_role: str | None
    federated_login: FederatedLogin | None


class TokenService:
    @staticmethod
    def create_token_pair(
        user: User,
        *,
        scopes: list[str] | None = None,
        active_role: str | None = None,
        federated_login: FederatedLogin | None = None,
    ) -> dict[str, object]:
        """access / refresh トークンを発行する。

        ``scopes`` を指定した場合もアクティブロールの権限との積集合に切り詰める。
        ``federated_login`` は SSO で始まったセッションのときだけ渡す（ADR-0036）。
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
            **_federation_claims(federated_login),
        }
        access = jwt.encode(
            {
                **base_claims,
                "type": TYPE_ACCESS,
                "scope": effective,
                "email": user.email,
                # ⚠ **検証が DB を引かないので、principal の材料はここに全部載せる**
                #   （ADR-0041）。載せ忘れた項目は、その経路でだけ空になる。
                "username": user.username,
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
    def verify_access_token_with_reason(cls, token: str) -> tuple[AuthenticatedPrincipal | None, str | None]:
        """アクセストークンを**署名とクレームだけ**で検証する（ADR-0041）。

        ⚠ **DB を引かない。** 止まっている利用者・外された権限・IdP からの停止は、
        ここでは分からない。**分かるのは次の更新のとき**で、それまでの上限が
        アクセストークンの寿命（既定 5 分）になる。

        ⚠ **この緩さを引き受けられるのは、更新の側が引き締めているからである。**
        :meth:`verify_refresh_token` は DB を引き、止まっていれば新しい
        アクセストークンを出さない。**止める判定はあちらの 1 点に集約してある。**
        """
        claims, reason = cls._decode(token)
        if claims is None:
            return None, reason
        if claims.get("type") != TYPE_ACCESS:
            return None, "not_access_token"
        try:
            user_id = int(claims.get("sub", ""))
        except ValueError:
            return None, "token_invalid"
        return (
            AuthenticatedPrincipal(
                user_id=user_id,
                email=str(claims.get("email") or ""),
                username=str(claims.get("username") or ""),
                permissions=frozenset(claims.get("scope") or ()),
                active_role=_active_role_of(claims),
            ),
            None,
        )

    @classmethod
    def verify_refresh_token(cls, token: str, *, session: Session) -> RefreshedSession | None:
        """更新対象のユーザーと、そのセッションのアクティブロール・入り口を返す。

        ⚠ **止める判定はここに集約してある**（ADR-0041）。アクセストークンの検証は
        DB を引かないので、**止まっている利用者を止められるのはこの 1 点だけ**である
        ——ここを緩めると、寿命による上限そのものが無くなる。
        """
        claims, _ = cls._decode(token)
        if claims is None or claims.get("type") != TYPE_REFRESH:
            return None
        user = cls._load_active_user(claims, session)
        if user is None:
            return None
        if _session_revoked(claims, session):
            return None
        return RefreshedSession(
            user=user,
            active_role=_active_role_of(claims),
            federated_login=_federated_login_of(claims),
        )

    @classmethod
    def session_is_revoked(cls, token: str, *, session: Session) -> bool:
        """このアクセストークンのセッションが IdP 側で止められているか（ADR-0041）。

        ⚠ **普段の検証では呼ばない。** 呼ぶのは「新しいトークンを出す」経路だけで、
        そこだけは DB を引いて確かめる ——確かめないと、止められた利用者が
        出し直しを繰り返すだけで寿命の上限を破れる。
        """
        claims, _ = cls._decode(token)
        if claims is None or claims.get("type") != TYPE_ACCESS:
            return False
        return _session_revoked(claims, session)

    @classmethod
    def federated_login_of(cls, token: str) -> FederatedLogin | None:
        """検証済みのアクセストークンから、IdP 側のセッションを読む。

        ロールの切り替えで新しいトークンを出すときに引き継ぐためのもの
        （引き継がないと、切り替えた瞬間に停止の伝播から外れる）。
        """
        claims, _ = cls._decode(token)
        if claims is None or claims.get("type") != TYPE_ACCESS:
            return None
        return _federated_login_of(claims)

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


def _federation_claims(federated_login: FederatedLogin | None) -> dict[str, object]:
    """IdP 側のセッションをクレームへ写す。ローカルのログインでは何も載せない。"""
    if federated_login is None:
        return {}
    claims: dict[str, object] = {
        CLAIM_FEDERATED_ISSUER: federated_login.session.issuer,
        CLAIM_FEDERATED_SUBJECT: federated_login.session.subject,
        CLAIM_FEDERATED_ISSUED_AT: _to_microseconds(federated_login.started_at),
    }
    if federated_login.session.session_id is not None:
        claims[CLAIM_SESSION_ID] = federated_login.session.session_id
    return claims


def _federated_login_of(claims: dict[str, Any]) -> FederatedLogin | None:
    """クレームから IdP 側のセッションを読む。載っていなければ ``None``。"""
    issuer = claims.get(CLAIM_FEDERATED_ISSUER)
    subject = claims.get(CLAIM_FEDERATED_SUBJECT)
    started_at = claims.get(CLAIM_FEDERATED_ISSUED_AT)
    if not isinstance(issuer, str) or not isinstance(subject, str) or not isinstance(started_at, int):
        return None
    session_id = claims.get(CLAIM_SESSION_ID)
    return FederatedLogin(
        session=FederatedSession(
            issuer=issuer,
            subject=subject,
            session_id=session_id if isinstance(session_id, str) else None,
        ),
        started_at=_from_microseconds(started_at),
    )


def _to_microseconds(moment: datetime) -> int:
    """naive な UTC をエポックからのマイクロ秒へ（CLAUDE.md「時刻の契約」）。"""
    return int(moment.replace(tzinfo=UTC).timestamp() * 1_000_000)


def _from_microseconds(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000, UTC).replace(tzinfo=None)


def _session_revoked(claims: dict[str, Any], session: Session) -> bool:
    """このトークンのセッションが IdP 側で止められていないか（ADR-0036）。"""
    check = CheckSessionRevocation(revocations=SqlSessionRevocationRepository(session))
    return check.execute(_federated_login_of(claims))


def _active_role_of(claims: dict[str, Any]) -> str | None:
    """クレームのアクティブロール。無い・文字列でないものは「すべてのロール」扱い。

    クレームを持たない発行済みトークン（この機能より前のもの）もそのまま使える。
    """
    value = claims.get(CLAIM_ACTIVE_ROLE)
    return value if isinstance(value, str) else None


__all__ = [
    "CLAIM_ACTIVE_ROLE",
    "CLAIM_FEDERATED_ISSUED_AT",
    "CLAIM_FEDERATED_ISSUER",
    "CLAIM_FEDERATED_SUBJECT",
    "CLAIM_SESSION_ID",
    "TYPE_ACCESS",
    "TYPE_REFRESH",
    "RefreshedSession",
    "TokenService",
]
