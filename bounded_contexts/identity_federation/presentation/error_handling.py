"""Mapping of domain exceptions -> HTTP responses.

This only handles **routes that return JSON** (``POST /api/auth/sso/token``,
``POST /api/auth/sso/backchannel-logout``, ``/api/auth/sso/link``).
``/login`` and ``/callback``, used in browser navigations, catch exceptions in the router itself
and turn them into redirects to the login screen (the SPA can't read JSON there).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bounded_contexts.identity_federation.domain.exceptions import (
    DpopProofRejectedError,
    IdentityFederationError,
    IdentityProviderUnavailableError,
    InvalidLogoutTokenError,
    SsoAlreadyLinkedError,
    SsoIdentityNotLinkedError,
    SsoIdentityTakenError,
    SsoLastEntranceError,
    SsoNotConfiguredError,
    SsoTicketNotFoundError,
)
from presentation.fastapi.error_handling import log_failed_request

_STATUS_BY_ERROR: dict[type[IdentityFederationError], int] = {
    IdentityProviderUnavailableError: status.HTTP_502_BAD_GATEWAY,
    SsoNotConfiguredError: status.HTTP_404_NOT_FOUND,
    SsoTicketNotFoundError: status.HTTP_401_UNAUTHORIZED,
    # Logout notices are sent by the IdP, not the user. A 401 would read as "re-authenticate",
    # so per the spec it's returned as "invalid request" (Back-Channel Logout 1.0 §2.8).
    InvalidLogoutTokenError: status.HTTP_400_BAD_REQUEST,
    # Unlinking / binding (ADR-0077 §5). ⚠ **Not 401** — the caller has passed
    # authentication, and reading it as "re-authenticate" makes the user repeat pointless actions.
    SsoIdentityNotLinkedError: status.HTTP_404_NOT_FOUND,
    SsoIdentityTakenError: status.HTTP_409_CONFLICT,
    SsoAlreadyLinkedError: status.HTTP_409_CONFLICT,
    SsoLastEntranceError: status.HTTP_409_CONFLICT,
}


#: ``WWW-Authenticate`` attached to 401. A DPoP proof error signals the app to fix its clock and
#: rebuild the proof (RFC 9449 §7.1, ADR-0103).
_CHALLENGES: dict[type[IdentityFederationError], dict[str, str]] = {
    DpopProofRejectedError: {"WWW-Authenticate": 'DPoP error="invalid_dpop_proof", algs="ES256"'},
}


def status_for(error: IdentityFederationError) -> int:
    """Default is 401. Every SSO failure means the login did not go through."""
    return _STATUS_BY_ERROR.get(type(error), status.HTTP_401_UNAUTHORIZED)


def register_identity_federation_error_handler(app: FastAPI) -> None:
    @app.exception_handler(IdentityFederationError)
    async def _handle(request: Request, error: IdentityFederationError) -> JSONResponse:
        status_code = status_for(error)
        log_failed_request(request, status_code, error.code)
        headers = _CHALLENGES.get(type(error))
        return JSONResponse(status_code=status_code, content={"detail": {"error": error.code}}, headers=headers)


__all__ = ["register_identity_federation_error_handler", "status_for"]
