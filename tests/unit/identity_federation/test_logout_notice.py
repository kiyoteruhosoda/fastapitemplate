"""Whether it is valid as a logout notice (ADR-0077 §3).

Signature verification is the Infrastructure layer's job, so only the **shape of the contents** is checked here.
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
    """A notice without ``sid`` means "this user was stopped"; it cannot tell sessions apart."""
    claims = _claims()
    del claims["sid"]
    assert LogoutNotice.from_claims(claims, issuer=_ISSUER).session.session_id is None


def test_a_token_without_the_logout_event_is_refused() -> None:
    not_a_logout: tuple[Any, ...] = ({}, {"http://example.test/other": {}}, "backchannel-logout", None)
    for events in not_a_logout:
        with pytest.raises(InvalidLogoutTokenError):
            LogoutNotice.from_claims(_claims(events=events), issuer=_ISSUER)


def test_an_id_token_is_refused() -> None:
    """⚠ Anything with ``nonce`` is an ID token. Accepting it would let anyone sign out another
    person's session just by sending back a legitimately received ID token."""
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(_claims(nonce="n-1"), issuer=_ISSUER)


def test_a_token_naming_nobody_is_refused() -> None:
    claims = _claims()
    del claims["sub"]
    del claims["sid"]
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims, issuer=_ISSUER)


def test_a_token_without_a_jti_is_refused() -> None:
    """Without ``jti``, resends cannot be rejected (the same notice would work any number of times)."""
    claims = _claims()
    del claims["jti"]
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims, issuer=_ISSUER)
