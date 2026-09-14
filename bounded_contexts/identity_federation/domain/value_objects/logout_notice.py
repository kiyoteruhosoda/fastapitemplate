"""IdP から届いた「このセッションを止めろ」（OpenID Connect Back-Channel Logout 1.0）。

``logout_token`` の**署名・発行者・対象者・有効期限**を確かめるのは Infrastructure 層
（JWT の話なので）。ここが見るのは**それ以外の 4 つ**で、どれも仕様が明示的に
求めているものである（§2.6）。

- ``events`` に back-channel logout のイベントが入っていること
  ——入っていない JWT は「ログアウトの通知」ではない
- ``nonce`` が**入っていない**こと ——入っているものは ID トークンであり、
  それを受け付けると**手元の ID トークンを投げ返すだけでログアウトを起こせる**
- ``sub`` か ``sid`` のどちらかがあること ——どちらも無ければ誰を止めるのか決まらない
- ``jti`` があること ——再送を弾く鍵になる（ADR-0024 は再送しても同じ ``jti`` を使う）
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidLogoutTokenError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)

#: back-channel logout のイベント名（OpenID Connect Back-Channel Logout 1.0 §2.4）。
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


@dataclass(frozen=True)
class LogoutNotice:
    """検証を通った通知。``jti`` は配送の identity で、再送でも変わらない。"""

    jti: str
    session: FederatedSession

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any], *, issuer: str) -> LogoutNotice:
        """検証済みのクレームから組み立てる。成立しないものは例外にする。"""
        _ensure_logout_event(claims)
        _ensure_not_an_id_token(claims)
        jti = _text(claims.get("jti"))
        if not jti:
            raise InvalidLogoutTokenError
        subject = _text(claims.get("sub"))
        session_id = _text(claims.get("sid"))
        if not subject and not session_id:
            raise InvalidLogoutTokenError
        return cls(
            jti=jti,
            session=FederatedSession(issuer=issuer, subject=subject, session_id=session_id or None),
        )


def _ensure_logout_event(claims: Mapping[str, Any]) -> None:
    events = claims.get("events")
    if not isinstance(events, Mapping) or LOGOUT_EVENT not in events:
        raise InvalidLogoutTokenError


def _ensure_not_an_id_token(claims: Mapping[str, Any]) -> None:
    """``nonce`` を持つものは受け取らない（仕様が MUST NOT としている）。

    ID トークンと logout token は署名鍵も発行者も対象者も同じなので、**この 1 点だけ**が
    両者を分ける。落とすと、正規に受け取った ID トークンを送り返すだけで
    他人のセッションを落とせる。
    """
    if "nonce" in claims:
        raise InvalidLogoutTokenError


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["LOGOUT_EVENT", "LogoutNotice"]
