"""CSRF protection for cookie-authenticated requests (double-submit token; ADR-0076 §4).

Once tokens move into httpOnly cookies, the browser **attaches the cookie even to requests we
never meant to send**. `SameSite=Lax` stops POSTs from other sites but not from parties treated
as same-site (e.g. a taken-over subdomain). For state-changing requests only, the same value is
required in both the cookie and a header.

**Required only for "state-changing requests authenticated by cookie".**

- Not required for reads (GET / HEAD / OPTIONS): the attacker cannot read the result.
- Not required for requests with an ``Authorization`` header: **headers are not sent
  automatically**, so CSRF is not possible in the first place (for curl, CI, other apps).
- **Not required for the entrances themselves (login, passkey, SSO exchange, password reset,
  logout).** These do not act on an existing session; they create or discard one. Requiring it
  here would mean **simply logging in again with another account gets 403** (the previous
  session's cookie is still there). Login CSRF remains a concern, but password login needs
  credentials, and SSO is closed off separately by the round-trip state cookie (ADR-0077 §1).
  Logout only drops cookies, so the harm is small.

The token cannot be sent unless JavaScript can read it, so this cookie alone is not
``httpOnly``. **It is not the access token**: leaking it achieves nothing on its own.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from presentation.fastapi.dependencies.auth import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
ERROR_CODE = "csrf_token_invalid"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Endpoints that create or discard a session. Excluded since they don't act on an existing one.
_ENTRANCES = frozenset(
    {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/passkey/challenge",
        "/api/auth/passkey/login",
        "/api/auth/sso/token",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    }
)


def _authenticated_by_cookie(request: Request) -> bool:
    if request.headers.get("Authorization"):
        return False
    return bool(request.cookies.get(ACCESS_TOKEN_COOKIE) or request.cookies.get(REFRESH_TOKEN_COOKIE))


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in _SAFE_METHODS or request.url.path in _ENTRANCES or not _authenticated_by_cookie(request):
            return await call_next(request)
        sent = request.headers.get(CSRF_HEADER) or ""
        expected = request.cookies.get(CSRF_COOKIE) or ""
        # Check **non-empty** as well as equal. Passing when both are empty would let through
        # anyone who dropped the cookie.
        if not expected or not compare_digest(sent, expected):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": {"error": ERROR_CODE}},
            )
        return await call_next(request)


__all__ = ["CSRF_COOKIE", "CSRF_HEADER", "ERROR_CODE", "CsrfMiddleware"]
