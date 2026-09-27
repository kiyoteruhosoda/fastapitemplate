"""停止の通知として成立しているか（ADR-0036）。

署名の検証は Infrastructure 層の仕事なので、ここで見るのは**中身の形**だけ。
"""

from __future__ import annotations

from typing import Any

import pytest

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidLogoutTokenError,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LOGOUT_EVENT,
    LogoutNotice,
)

_ISSUER = "https://idp.example.test"


def _claims(**overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": "rp",
        "sub": "idp-subject",
        "sid": "session-1",
        "jti": "delivery-1",
        "events": {LOGOUT_EVENT: {}},
    }
    claims.update(overrides)
    return claims


def test_a_notice_carries_the_session_it_names() -> None:
    notice = LogoutNotice.from_claims(_claims(), issuer=_ISSUER)
    assert notice.jti == "delivery-1"
    assert notice.session.issuer == _ISSUER
    assert notice.session.subject == "idp-subject"
    assert notice.session.session_id == "session-1"


def test_without_a_sid_the_whole_subject_is_named() -> None:
    """``sid`` の無い通知は「この利用者を止めた」。セッションの区別が付かない。"""
    claims = _claims()
    del claims["sid"]
    assert LogoutNotice.from_claims(claims, issuer=_ISSUER).session.session_id is None


def test_a_token_without_the_logout_event_is_refused() -> None:
    not_a_logout: tuple[Any, ...] = ({}, {"http://example.test/other": {}}, "backchannel-logout", None)
    for events in not_a_logout:
        with pytest.raises(InvalidLogoutTokenError):
            LogoutNotice.from_claims(_claims(events=events), issuer=_ISSUER)


def test_an_id_token_is_refused() -> None:
    """⚠ ``nonce`` があるものは ID トークン。受け付けると、正規に受け取った
    ID トークンを送り返すだけで他人のセッションを落とせる。"""
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(_claims(nonce="n-1"), issuer=_ISSUER)


def test_a_token_naming_nobody_is_refused() -> None:
    claims = _claims()
    del claims["sub"]
    del claims["sid"]
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims, issuer=_ISSUER)


def test_a_token_without_a_jti_is_refused() -> None:
    """``jti`` が無いと再送を弾けない（同じ通知が何度でも効いてしまう）。"""
    claims = _claims()
    del claims["jti"]
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims, issuer=_ISSUER)
