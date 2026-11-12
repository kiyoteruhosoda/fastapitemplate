"""What is set when a login succeeds (ADR-0076 §4).

There are three paths that issue tokens (password / passkey / SSO ticket exchange).
**SSO logins get no refresh token** (access token only; ADR-0104).
**How they are set lives in this one place**: if even one path sets cookies differently, that
entrance alone ends up without CSRF protection, unable to refresh, and so on.

⚠ **Tokens are not put in the response body.** Cookies are sent automatically, so returning them
in the body too would let XSS call ``POST /api/auth/refresh`` and read the new token, defeating
``httpOnly``. Only the lifetime is returned, which the SPA uses to time its refresh.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session, object_session

from presentation.fastapi.dependencies.auth import (
    clear_refresh_cookies,
    set_access_token_cookie,
    set_logout_token_cookie,
    set_refresh_token_cookie,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE
from presentation.fastapi.schemas.auth import SessionResponse
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.session_carry_over import FRESH_SIGN_IN, SessionCarryOver
from shared.infrastructure.models import User
from shared.infrastructure.tenant_scope import tenant_admits
from shared.kernel.settings.settings import settings


def establish_session(
    response: Response,
    user: User,
    carry: SessionCarryOver = FRESH_SIGN_IN,
) -> SessionResponse:
    """Issue a token pair, set it in cookies, and return only the lifetime.

    ``carry`` is what carries over from the previous session (role, IdP session, time of the last
    actual sign-in). ⚠ **Refresh and role switch must always carry all of it**
    (:mod:`~presentation.fastapi.services.session_carry_over`). The default means "just came in
    through an entrance" and may be used as is only by the password and passkey entrances (SSO
    passes the IdP session).
    """
    from presentation.fastapi.services.token_service import RENEWAL_CARRY_SECONDS, TokenService

    ensure_tenant_admits(user)
    if carry.federated_login is not None:
        # SSO logins have no refresh token (ADR-0104). When it expires the UI asks the IdP
        # The cookie outlives the token: the round trip that continues after expiry reads the role
        # and sign-in time from it
        set_access_token_cookie(
            response,
            TokenService.create_access_token(user, carry=carry),
            max_age=RENEWAL_CARRY_SECONDS,
        )
        # Drop any refresh token issued before this mechanism (the refresh endpoint no longer
        # accepts it either)
        clear_refresh_cookies(response)
        _set_csrf_cookie(response)
        return SessionResponse(expires_in=settings.access_token_expires_seconds)
    session = object_session(user)
    if session is None:  # pragma: no cover - every caller passes a user loaded from the DB
        raise RuntimeError("the user must belong to a session")
    lifetime = refresh_sessions.lifetime_for(session, carry.refresh_session_id or carry.lifetime_from_session_id)
    pair = TokenService.create_token_pair(user, carry=carry, refresh_expires_at=lifetime.expires_at)
    set_access_token_cookie(response, str(pair["access_token"]))
    issued = refresh_sessions.IssuedRefreshToken(
        session_id=str(pair["refresh_session_id"]),
        jti=str(pair["refresh_jti"]),
        lifetime=lifetime,
    )
    if _record_refresh_session(session, user, issued, carry):
        set_refresh_token_cookie(response, str(pair["refresh_token"]), max_age=lifetime.max_age)
        set_logout_token_cookie(response, str(pair["logout_token"]), max_age=lifetime.max_age)
    _set_csrf_cookie(response)
    return SessionResponse(expires_in=settings.access_token_expires_seconds)


def _record_refresh_session(
    session: Session,
    user: User,
    issued: refresh_sessions.IssuedRefreshToken,
    carry: SessionCarryOver,
) -> bool:
    """Create or rotate the login record (ADR-0091). True if the refresh token cookie may be set."""
    if carry.refresh_session_id is None:
        refresh_sessions.begin(session, issued=issued, user_id=user.id)
        return True
    rotated = refresh_sessions.rotate(session, issued=issued, expected_jti=carry.presented_jti)
    # ⚠ **Don't hold the row lock until the response.** If refreshes of the same login arrive at
    #   once, the later one waits on this row until commit. The commit happens after the response
    #   (``get_db`` teardown), so commit here to shorten the wait.
    session.commit()
    return rotated


TENANT_SUSPENDED = "tenant_suspended"


def ensure_tenant_admits(user: User) -> None:
    """No tokens for members of a suspended tenant (ADR-0079 §1). Every entrance goes through here."""
    session = object_session(user)
    if session is not None and not tenant_admits(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TENANT_SUSPENDED})


def _set_csrf_cookie(response: Response) -> None:
    """The CSRF double-submit token. **This one alone is readable from JavaScript.**

    It can't be put in a header unless it is readable. Leaking it achieves nothing on its own, so
    it is not treated like the access token.
    """
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=settings.refresh_token_expires_seconds,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


__all__ = ["establish_session"]
