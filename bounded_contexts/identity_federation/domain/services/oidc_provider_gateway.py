"""Interface for round trips with the OpenID Provider (implemented in Infrastructure).

Protocol details (discovery, token endpoint, JWKS signature verification) are kept in the
implementation; domain and application only know two things: "build the authorization URL"
and "exchange the authorization code for claims". The claims returned are **verified** and
handled as plain ``dict`` (no HTTP / JWT library types leak inward).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)


@dataclass(frozen=True)
class AuthorizationRequest:
    """Inputs for sending the browser to the IdP."""

    provider: IdentityProvider
    state: str
    nonce: str
    code_challenge: str
    #: Required authentication strength (``acr_values``). Empty = none required (ADR-0076 §3 decision 1).
    acr_values: tuple[str, ...] = ()
    #: Try silently (``prompt=none``. ADR-0077 §9). If false, ``prompt`` is not added.
    silent: bool = False


@dataclass(frozen=True)
class EndSessionRequest:
    """Inputs for carrying sign-out through to the IdP (RP-Initiated Logout 1.0).

    No ``id_token_hint``. This template doesn't keep the ID token after verifying it, so
    **it can't send what it doesn't have**. Instead it identifies with the pair ``client_id`` and
    ``post_logout_redirect_uri`` (the OP checks that this pair is registered).
    Keeping it would mean adding a column, so apps that need it decide that separately.
    """

    provider: IdentityProvider
    #: Where to return after sign-out. Omitted if empty (stops at the OP's own completion page).
    post_logout_redirect_uri: str = ""


@dataclass(frozen=True)
class LogoutTokenVerification:
    """Inputs for verifying a ``logout_token`` received from the IdP (ADR-0077 §3)."""

    provider: IdentityProvider
    logout_token: str


@dataclass(frozen=True)
class CodeExchange:
    """Inputs for redeeming a returned authorization code."""

    provider: IdentityProvider
    code: str
    code_verifier: str
    nonce: str


class OidcProviderGateway(Protocol):
    def authorization_url(self, request: AuthorizationRequest) -> str:
        """Build the URL to the authorization endpoint.

        If the IdP is unreachable,
        :class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`.
        """

    def end_session_url(self, request: EndSessionRequest) -> str | None:
        """URL to send to for sign-out. **``None`` if the IdP doesn't support it.**

        Some OPs lack ``end_session_endpoint`` in discovery, so callers should simply treat
        ``None`` as "can't go through with this IdP" (not a failure).
        """

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        """Exchange the authorization code for verified claims.

        Returns after checking the ID token's signature, issuer, audience and ``nonce``.
        Failures are ``InvalidIdTokenError`` / ``IdentityProviderUnavailableError``.
        """

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:
        """Verify the ``logout_token``'s signature, issuer, audience and expiry and return the claims.

        Same key, issuer and audience as the ID token, so **this is as far as JWT verification
        can go**. Judging "this is a logout notice" is done by
        :class:`~bounded_contexts.identity_federation.domain.value_objects.logout_notice.LogoutNotice`
        Failures are ``InvalidLogoutTokenError`` / ``IdentityProviderUnavailableError``.
        """


__all__ = [
    "AuthorizationRequest",
    "CodeExchange",
    "EndSessionRequest",
    "LogoutTokenVerification",
    "OidcProviderGateway",
]
