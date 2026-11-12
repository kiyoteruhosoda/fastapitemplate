"""Follow-up of the round trip that silently continues an expired login (ADR-0104).

The screen (SPA) opens a hidden frame (iframe) and round-trips from ``/api/auth/sso/login?frame=1`` to the
IdP with ``prompt=none``. The return (``/callback``) sets cookies without a redemption ticket and sends to
**the result page**. The screen learns the result by reading the frame's location (same origin) — no
script runs inside the frame, so CSP ``script-src 'self'`` needn't be relaxed.

Three results.

- ``renewed`` — continued (a new access token cookie was set)
- ``declined`` — not signed in at the IdP, not permitted, or switched to a different person.
  The screen goes to the login screen
- ``failed`` — the round trip broke (round-trip state unreadable, IdP unreachable). The screen
  goes to the login screen

⚠ **Only our own origin may frame these.** The round-trip endpoints (``/login``, ``/callback``) and the
result page get ``frame-ancestors 'self'``. Other responses stay ``'none'`` as before (ADR-0073 §5).
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlencode

from fastapi import Response
from fastapi.responses import HTMLResponse

#: Result page. Keep in sync with the screen (``frontend/src/services/silentRenewal.ts``)
RESULT_PATH = "/api/auth/sso/renewed"
RESULT_PARAM = "result"

#: CSP for responses opened inside the frame. The result page loads nothing
_FRAMED_CSP = "default-src 'none'; frame-ancestors 'self'"


class RenewalResult(StrEnum):
    RENEWED = "renewed"
    DECLINED = "declined"
    FAILED = "failed"


def allow_same_origin_framing(response: Response) -> Response:
    """Mark as frameable only by our own origin (global protective headers use ``setdefault``, so
    they remain)."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = _FRAMED_CSP
    return response


def result_location(result: RenewalResult) -> str:
    """URL of the result page."""
    return f"{RESULT_PATH}?{urlencode({RESULT_PARAM: result.value})}"


def result_page() -> HTMLResponse:
    """Result page. No content needed (the screen only reads the URL)."""
    response = HTMLResponse("<!doctype html><title>sso</title>", headers={"Cache-Control": "no-store"})
    allow_same_origin_framing(response)
    return response


__all__ = ["RESULT_PATH", "RenewalResult", "allow_same_origin_framing", "result_location", "result_page"]
