"""JWT の発行・検証（access / refresh の2トークン）。

- scope クレームはユーザーの保有権限の範囲内。未指定・空 = 権限なし。
- ``active_role`` クレームは「いまどのロールで操作しているか」（ADR-0078 §1）。
  ``None`` は「すべてのロール」＝保有権限の和集合。指定されている場合、scope は
  そのロール 1 つ分の権限に絞られる。切り替えは新しいトークンの発行で行う。
- ``fed_iss`` / ``fed_sub`` / ``sid`` / ``fed_iat`` は、IdP 経由で始まったセッションの
  宛名と**始まった時刻**（ADR-0077 §3）。**検証のたびに「止められていないか」を照合
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
from presentation.fastapi.services.session_carry_over import FRESH_SIGN_IN, SessionCarryOver
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.infrastructure.tenant_scope import tenant_admits
from shared.kernel.settings.settings import settings

_ALGORITHM = "HS256"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
# アクティブロール名を載せるクレーム名（access / refresh の双方に入れる。
# refresh に無いと、トークン更新のたびに「すべてのロール」へ戻ってしまう）
CLAIM_ACTIVE_ROLE = "active_role"
# IdP 側のセッションの宛名（ADR-0077 §3）。``sid`` だけ OIDC と同じ綴りにする
# （ID トークンから写した値であることを読み取れるようにするため）。
CLAIM_FEDERATED_ISSUER = "fed_iss"
CLAIM_FEDERATED_SUBJECT = "fed_sub"
CLAIM_SESSION_ID = "sid"
# セッションが始まった時刻（エポックからのマイクロ秒）。``iat`` は秒までしか持たず、
# 止めた直後の同じ秒に入り直した利用者を巻き添えにするため、別に持つ。
CLAIM_FEDERATED_ISSUED_AT = "fed_iat"
# 本人が最後に実際にサインインした時刻（エポック秒。OIDC と同じ綴り。ADR-0076 §10）。
# 更新・ロールの切り替えでは引き継ぎ、新しくしない。
CLAIM_AUTHENTICATED_AT = "auth_time"
# 所属するテナント（ADR-0079 §1）。テナントに属さない利用者は null。
# ⚠ **クレームが無いトークン（テナントより前のもの）は受け付けない。** null と読むと
# 「どのテナントの中身も見えない」まま寿命まで過ごすことになるので、401 で更新させる
# （更新は DB を引いて、いまの所属で出し直す）。
CLAIM_TENANT = "tenant"
#: 機械の口から出したトークンの印（名乗った機械の ``client_id``。ADR-0087）。人のトークンには載らない。
#: ⚠ これが載ったトークンは、scope で守られた口（``require_permission``）でしか通らない。
CLAIM_MACHINE_CLIENT = "machine_client"
#: ``auth_time`` を持たない（この仕組みより前の）トークンの扱い。「ずっと前」とみなす
SIGNED_IN_LONG_AGO = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class MachineAccessToken:
    """機械の口で出したトークン（ADR-0087）。"""

    token: str
    expires_in: int
    #: 実際に載った scope（許可簿の操作と利用者の権限の重なり）
    scopes: list[str]


@dataclass(frozen=True)
class RefreshedSession:
    """更新の対象。**入り口（``federated_session``）も一緒に返す**（ADR-0077 §3）。

    落とすと、更新のたびに IdP のセッションの宛名が消え、**トークンを 1 回更新する
    だけで停止の伝播をすり抜けられる**。
    """

    user: User
    active_role: str | None
    federated_login: FederatedLogin | None
    #: 本人が最後に実際にサインインした時刻（ADR-0076 §10）。更新でも引き継ぐ
    authenticated_at: datetime = SIGNED_IN_LONG_AGO

    @property
    def carry(self) -> SessionCarryOver:
        """新しいトークンへ引き継ぐもの（ロール・入り口・サインインした時刻）。"""
        return SessionCarryOver(
            active_role=self.active_role,
            federated_login=self.federated_login,
            authenticated_at=self.authenticated_at,
        )


class TokenService:
    @staticmethod
    def create_token_pair(
        user: User,
        *,
        scopes: list[str] | None = None,
        carry: SessionCarryOver = FRESH_SIGN_IN,
    ) -> dict[str, object]:
        """access / refresh トークンを発行する。

        ``scopes`` を指定した場合もアクティブロールの権限との積集合に切り詰める。
        ``federated_login`` は SSO で始まったセッションのときだけ渡す（ADR-0077 §3）。
        """
        granted = user.permission_codes_of(carry.active_role)
        effective = sorted(granted if scopes is None else granted & set(scopes))
        now = datetime.now(UTC)
        base_claims = {
            "sub": str(user.id),
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "iat": now,
            # ``None`` は「いまサインインした」（パスワード・パスキー・SSO の入口）
            CLAIM_AUTHENTICATED_AT: int((carry.authenticated_at or now).timestamp()),
            CLAIM_ACTIVE_ROLE: carry.active_role,
            CLAIM_TENANT: user.tenant_id,
            **_federation_claims(carry.federated_login),
        }
        access = jwt.encode(
            {
                **base_claims,
                "type": TYPE_ACCESS,
                "scope": effective,
                "email": user.email,
                # ⚠ **検証が DB を引かないので、principal の材料はここに全部載せる**
                #   （ADR-0076 §5）。載せ忘れた項目は、その経路でだけ空になる。
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
    def create_machine_access_token(user: User, *, client_id: str, operations: frozenset[str]) -> MachineAccessToken:
        """機械の口のアクセストークン（ADR-0087）。**リフレッシュトークンは出さない**（機械は取り直せばよい）。

        scope は「利用者の全ロールの権限」と「許可簿の操作」の**両方にあるものだけ**。
        ⚠ ``auth_time`` は「ずっと前」にする（入り直したばかりが要る操作を、機械は通れない。ADR-0076 §10）。
        """
        effective = sorted(user.permission_codes_of(None) & operations)
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iss": settings.access_token_issuer,
                "aud": settings.access_token_audience,
                "iat": now,
                "exp": now + timedelta(seconds=settings.access_token_expires_seconds),
                "type": TYPE_ACCESS,
                "scope": effective,
                "email": user.email,
                "username": user.username,
                CLAIM_AUTHENTICATED_AT: int(SIGNED_IN_LONG_AGO.timestamp()),
                CLAIM_ACTIVE_ROLE: None,
                CLAIM_TENANT: user.tenant_id,
                CLAIM_MACHINE_CLIENT: client_id,
            },
            settings.jwt_secret_key,
            algorithm=_ALGORITHM,
        )
        return MachineAccessToken(token=token, expires_in=settings.access_token_expires_seconds, scopes=effective)

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
        """アクセストークンを**署名とクレームだけ**で検証する（ADR-0076 §5）。

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
        if CLAIM_TENANT not in claims:
            return None, "token_outdated"
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
                authenticated_at=_authenticated_at_of(claims),
                tenant_id=_tenant_of(claims),
                machine_client_id=_machine_client_of(claims),
            ),
            None,
        )

    @classmethod
    def verify_refresh_token(cls, token: str, *, session: Session) -> RefreshedSession | None:
        """更新対象のユーザーと、そのセッションのアクティブロール・入り口を返す。

        ⚠ **止める判定はここに集約してある**（ADR-0076 §5）。アクセストークンの検証は
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
            authenticated_at=_authenticated_at_of(claims),
        )

    @classmethod
    def session_is_revoked(cls, token: str, *, session: Session) -> bool:
        """このアクセストークンのセッションが IdP 側で止められているか（ADR-0076 §5）。

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
        # 止めたテナントの人には出し直さない（ADR-0079 §1）。手元の 1 枚は寿命まで
        if not tenant_admits(session, user):
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
    """このトークンのセッションが終わっていないか。

    終わっているのは 2 通り: パスワードを変えるなどして、利用者がそれより前の
    ログインを終わらせた（ADR-0076 §8）／IdP 側で止められた（ADR-0077 §3）。
    """
    if _issued_before_sessions_ended(claims, session):
        return True
    check = CheckSessionRevocation(revocations=SqlSessionRevocationRepository(session))
    return check.execute(_federated_login_of(claims))


def _issued_before_sessions_ended(claims: dict[str, Any], session: Session) -> bool:
    """利用者の区切り（``user_session_boundaries``）より前に出したトークンか（ADR-0076 §8）。

    ``iat`` は秒までしか持たないので、区切りも秒に切り捨てて比べる。切り上げると、
    区切った直後に**同じ秒の中で出し直した自分のトークン**まで断ってしまう。
    同じ秒の中で出た古いトークンは通るが、それは 1 秒に満たない幅である。
    """
    try:
        user = session.get(User, int(claims.get("sub", "")))
    except ValueError:
        return True
    if user is None or user.sessions_valid_from is None:
        return False
    issued_at = claims.get("iat")
    if not isinstance(issued_at, int):
        return True
    return issued_at < int(user.sessions_valid_from.replace(tzinfo=UTC).timestamp())


def _authenticated_at_of(claims: dict[str, Any]) -> datetime:
    """本人が最後に実際にサインインした時刻。無い・読めないものは「ずっと前」（ADR-0076 §10）。

    ⚠ **無いときに「いま」へ倒さない。** 倒すと、この仕組みより前のトークンが更新 1 回で
    「入り直したばかり」に化ける。
    """
    value = claims.get(CLAIM_AUTHENTICATED_AT)
    if not isinstance(value, int):
        return SIGNED_IN_LONG_AGO
    return datetime.fromtimestamp(value, UTC)


def _tenant_of(claims: dict[str, Any]) -> int | None:
    value = claims.get(CLAIM_TENANT)
    return value if isinstance(value, int) else None


def _machine_client_of(claims: dict[str, Any]) -> str | None:
    value = claims.get(CLAIM_MACHINE_CLIENT)
    return value if isinstance(value, str) and value else None


def _active_role_of(claims: dict[str, Any]) -> str | None:
    """クレームのアクティブロール。無い・文字列でないものは「すべてのロール」扱い。

    クレームを持たない発行済みトークン（この機能より前のもの）もそのまま使える。
    """
    value = claims.get(CLAIM_ACTIVE_ROLE)
    return value if isinstance(value, str) else None


__all__ = [
    "CLAIM_ACTIVE_ROLE",
    "CLAIM_AUTHENTICATED_AT",
    "CLAIM_FEDERATED_ISSUED_AT",
    "CLAIM_FEDERATED_ISSUER",
    "CLAIM_FEDERATED_SUBJECT",
    "CLAIM_MACHINE_CLIENT",
    "CLAIM_SESSION_ID",
    "CLAIM_TENANT",
    "SIGNED_IN_LONG_AGO",
    "TYPE_ACCESS",
    "TYPE_REFRESH",
    "MachineAccessToken",
    "RefreshedSession",
    "TokenService",
]
