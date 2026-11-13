"""Carry the authorization request's round-trip state in a signed cookie (ADR-0077 §1).

``state`` / ``nonce`` / PKCE ``code_verifier`` are needed **only while** the redirect leaves
for the IdP and comes back. Keeping a copy server-side would need a table and cleanup for
these short-lived values, and since everyone shares one table, "a party that merely knows
``state``" could complete the return (login CSRF). **Entrusting it to the browser in a
tamper-proof form** achieves the same defense with a single mechanism — without the cookie
there is nothing to match against.

- Signed with ``JWT_SECRET_KEY`` (HS256), same as the built-in JWT. Readable but **not
  modifiable**.
- Short expiry (``OIDC_LOGIN_TRANSACTION_TTL_SECONDS``).
- ``HttpOnly``. It holds the ``code_verifier``, so JavaScript must not read it.
- ``SameSite=Lax`` because the return from the IdP is **a cross-site GET navigation**
  (with ``Strict`` it isn't sent on return and legitimate logins always fail).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

import jwt
from fastapi import Response

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow

COOKIE_NAME = "sso_tx"
_ALGORITHM = "HS256"


def issue(response: Response, transaction: LoginTransaction, *, path: str) -> None:
    """Sign the round-trip state and put it in a cookie."""
    ttl = settings.oidc_login_transaction_ttl_seconds
    payload: dict[str, Any] = {
        "state": transaction.state,
        "nonce": transaction.nonce,
        "code_verifier": transaction.code_verifier,
        "redirect_to": transaction.redirect_to,
        "purpose": transaction.purpose.value,
        "user_id": transaction.user_id,
        "issuer": transaction.issuer,
        "silent": transaction.silent,
        "active_role": transaction.active_role,
        "auth_time": _epoch_of(transaction.authenticated_at),
        "passkey": transaction.signed_in_with_passkey,
        "exp": utcnow() + timedelta(seconds=ttl),
    }
    response.set_cookie(
        COOKIE_NAME,
        jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM),
        max_age=ttl,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=path,
    )


def read(raw: str | None) -> LoginTransaction | None:
    """Restore the round-trip state from the cookie. **Anything unrestorable silently becomes `None`.**

    Bad signature, expired, or simply missing all amount, from the caller's view, to one result:
    "this return cannot be accepted" (distinguishing them gives the user no more useful
    information, only clues to an attacker).
    """
    if not raw:
        return None
    try:
        claims = jwt.decode(raw, settings.jwt_secret_key, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    values = {key: claims.get(key) for key in ("state", "nonce", "code_verifier", "redirect_to")}
    if not all(isinstance(value, str) and value for value in values.values()):
        return None
    purpose = _purpose_of(claims.get("purpose"))
    if purpose is None:
        return None
    user_id = claims.get("user_id")
    issuer = claims.get("issuer")
    return LoginTransaction(
        **values,  # type: ignore[arg-type]
        purpose=purpose,
        user_id=user_id if isinstance(user_id, int) else None,
        issuer=issuer if isinstance(issuer, str) else "",
        # Cookies from before the silent attempt (ADR-0077 §9) lack it. Read as a normal round trip
        silent=claims.get("silent") is True,
        **_continued_of(claims),
    )


def _epoch_of(moment: datetime | None) -> int | None:
    return int(moment.timestamp()) if moment is not None else None


class _Continued(TypedDict):
    active_role: str | None
    authenticated_at: datetime | None
    signed_in_with_passkey: bool


def _continued_of(claims: dict[str, Any]) -> _Continued:
    """What the renewal round trip carries over (ADR-0104). Absent in other round trips and in
    cookies older than this mechanism."""
    role, auth_time = claims.get("active_role"), claims.get("auth_time")
    return _Continued(
        active_role=role if isinstance(role, str) else None,
        authenticated_at=datetime.fromtimestamp(auth_time, UTC) if isinstance(auth_time, int) else None,
        signed_in_with_passkey=claims.get("passkey") is True,
    )


def _purpose_of(raw: object) -> TransactionPurpose | None:
    """⚠ **Don't accept unknown purposes.**

    It is signed, so normally it can't be altered, but old cookies may remain when keys are
    reused. Falling back to the default would let "a round trip meant as a link complete as a
    login" — the fallback isn't necessarily the safe side, so refuse what can't be restored.
    """
    if raw is None:
        # Cookie issued before linking (ADR-0077 §5). Read as a login round trip.
        return TransactionPurpose.LOGIN
    if isinstance(raw, str) and raw in tuple(TransactionPurpose):
        return TransactionPurpose(raw)
    return None


def clear(response: Response, *, path: str) -> None:
    """The round trip is over, so drop it (on success or failure)."""
    response.delete_cookie(COOKIE_NAME, path=path)


__all__ = ["COOKIE_NAME", "clear", "issue", "read"]
