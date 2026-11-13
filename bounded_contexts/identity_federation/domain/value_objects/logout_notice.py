"""A "stop this session" received from the IdP (OpenID Connect Back-Channel Logout 1.0).

Checking the ``logout_token``'s **signature, issuer, audience and expiry** is Infrastructure's
job (it's about JWT). This checks **the other four**, all explicitly required by the spec
(§2.6).

- ``events`` contains the back-channel logout event
    — a JWT without it is not "a logout notice"
- ``nonce`` is **absent** — anything with it is an ID token, and accepting it would
    **allow triggering logout just by throwing back an ID token one holds**
- Either ``sub`` or ``sid`` is present — without both, who to stop is undetermined
- ``jti`` is present — the key for rejecting resends (ADR-0078 §3 uses the same ``jti`` on resend)
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

#: Back-channel logout event name (OpenID Connect Back-Channel Logout 1.0 §2.4).
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


@dataclass(frozen=True)
class LogoutNotice:
    """A notice that passed validation. ``jti`` is the delivery identity and doesn't change on resend."""

    jti: str
    session: FederatedSession

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any], *, issuer: str) -> LogoutNotice:
        """Build from verified claims. Raise if they don't form a valid notice."""
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
    """Don't accept anything with ``nonce`` (the spec says MUST NOT).

    ID tokens and logout tokens share signing key, issuer and audience, so **this one point**
    is what separates them. Dropping it would let anyone log out another person's session by
    sending back a legitimately received ID token.
    """
    if "nonce" in claims:
        raise InvalidLogoutTokenError


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["LOGOUT_EVENT", "LogoutNotice"]
