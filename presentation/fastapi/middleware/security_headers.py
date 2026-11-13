"""Add protective headers to every response (ADR-0073 §5).

Putting them in the front nginx would mean copying them into each derived app's copy in
deploy-repo, and copies get forgotten (a 2026-10-21 check found the trial copy had not even
copied the template's ``/metrics`` lockdown). When the app sets them itself, every app built from
the template gets them.

- **CSP** is ``default-src 'self'``. The UI uses no inline scripts or external resources. Only
  two exceptions: ``data:`` in ``img-src`` because the two-factor QR code is a ``data:`` image,
  and ``frame-ancestors 'none'`` because the app must not be framed.
- **``frame-src``** is our own origin plus names under the IdP issuer's parent domain
  (``https://*.<parent>``), so an expired login can be continued by asking the IdP in a hidden
  frame (ADR-0104). The round trip inside the frame moves from the issuer (e.g. ``identity.``) to
  the login screen's name (e.g. ``assay.``), so the issuer alone is not enough.
  Without an IdP it is just ``'self'``.
- ``/docs`` and ``/redoc`` load scripts from an external CDN, so **only CSP is omitted** there
  (other headers are set).
- **HSTS** only when ``SESSION_COOKIE_SECURE`` is enabled (= served over https). It is
  meaningless in http development, and forcing https on a name is the deployer's commitment.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.kernel.settings.settings import settings

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
STRICT_TRANSPORT_SECURITY = "max-age=31536000"
#: Names with this many labels or fewer (``localhost``, ``example.com``) don't take a parent
_BARE_NAME_LABELS = 2


def frame_sources(issuer: str) -> str:
    """The ``frame-src`` value (ADR-0104). Allows the parent one level above the issuer's name.
    Only ``'self'`` if it cannot be parsed.

    ``https://identity.nolumia.com/<tenant>`` -> ``'self' https://*.nolumia.com``. If the name has
    two labels or fewer (``localhost``, ``example.com``), only that name's origin is added.
    """
    parts = urlsplit(issuer)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "'self'"
    labels = parts.hostname.split(".")
    host = f"*.{'.'.join(labels[1:])}" if len(labels) > _BARE_NAME_LABELS else parts.hostname
    port = f":{parts.port}" if parts.port else ""
    return f"'self' {parts.scheme}://{host}{port}"


def content_security_policy(issuer: str) -> str:
    """The global CSP. Only ``frame-src`` varies with the IdP setting."""
    return f"{CONTENT_SECURITY_POLICY}; frame-src {frame_sources(issuer)}"


#: API documentation pages that load an external CDN. Only CSP is omitted
_DOCUMENTATION_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})

_ALWAYS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Don't leak the URL externally from a page opened via a reset link (``?token=``)
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # ⚠ Read settings **before the response**. Reading later, the settings reload can return
        #   the connection before the request's DB write and roll back the uncommitted write
        #   (SQLite with a shared connection)
        served_over_https = settings.session_cookie_secure
        policy = content_security_policy(settings.oidc_issuer if settings.oidc_enabled else "")
        response = await call_next(request)
        for name, value in _ALWAYS.items():
            response.headers.setdefault(name, value)
        if request.url.path not in _DOCUMENTATION_PATHS:
            # If an individual response has its own (stricter) CSP, keep it
            response.headers.setdefault("Content-Security-Policy", policy)
        if served_over_https:
            response.headers.setdefault("Strict-Transport-Security", STRICT_TRANSPORT_SECURITY)
        return response


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "STRICT_TRANSPORT_SECURITY",
    "SecurityHeadersMiddleware",
    "content_security_policy",
    "frame_sources",
]
