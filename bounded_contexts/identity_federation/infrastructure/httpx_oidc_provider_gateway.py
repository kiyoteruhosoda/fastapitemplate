"""Round trips with the OpenID Provider (httpx + PyJWT).

Implements the authorization code flow + PKCE (``S256``). The implicit flow is not used —
the ID token would pass through the browser URL and remain in history and access logs.

The ID token is **verified against the JWKS public key**, and the issuer, audience and
``nonce`` are checked. For IdPs that don't put groups or email in the ID token,
UserInfo is also fetched to fill in missing claims.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    InvalidIdTokenError,
    InvalidLogoutTokenError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
    EndSessionRequest,
    LogoutTokenVerification,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)
from bounded_contexts.identity_federation.infrastructure.client_assertion import (
    ASSERTION_TYPE,
    ClientAssertionRequest,
    build_client_assertion,
)
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import (
    USER_AGENT,
    OidcMetadataCache,
    ProviderMetadata,
)

logger = logging.getLogger(__name__)

_BASIC_AUTH = "client_secret_basic"


class HttpxOidcProviderGateway:
    def __init__(self, *, metadata: OidcMetadataCache | None = None, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds
        self._metadata = metadata if metadata is not None else OidcMetadataCache(timeout_seconds=timeout_seconds)

    # ------------------------------------------------------------------
    # Sending out
    # ------------------------------------------------------------------

    def authorization_url(self, request: AuthorizationRequest) -> str:
        provider = request.provider
        metadata = self._metadata.metadata(provider.issuer)
        parameters = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "scope": provider.scope_parameter,
            "state": request.state,
            "nonce": request.nonce,
            "code_challenge": request.code_challenge,
            "code_challenge_method": "S256",
        }
        if request.acr_values:
            # Space-separated (OIDC Core §3.1.2.1). When nothing is required, omit the parameter entirely
            # — some IdPs treat an empty string as "an empty requirement".
            parameters["acr_values"] = " ".join(request.acr_values)
        if request.silent:
            # If signed in at the IdP a code comes back directly; if not, it returns silently with
            # ``error=login_required`` etc. (OIDC Core §3.1.2.1. ADR-0077 §9).
            parameters["prompt"] = "none"
        separator = "&" if "?" in metadata.authorization_endpoint else "?"
        return f"{metadata.authorization_endpoint}{separator}{urlencode(parameters)}"

    def end_session_url(self, request: EndSessionRequest) -> str | None:
        provider = request.provider
        metadata = self._metadata.metadata(provider.issuer)
        if not metadata.end_session_endpoint:
            # The OP doesn't support it. Return None so the caller knows it can't go through.
            return None
        parameters = {"client_id": provider.client_id}
        if request.post_logout_redirect_uri:
            # ⚠ **Only used if the URI is registered with the OP.** If unregistered nothing fails;
            #   it stops at the OP's own completion page (the sign-out itself still works).
            parameters["post_logout_redirect_uri"] = request.post_logout_redirect_uri
        separator = "&" if "?" in metadata.end_session_endpoint else "?"
        return f"{metadata.end_session_endpoint}{separator}{urlencode(parameters)}"

    # ------------------------------------------------------------------
    # Redemption
    # ------------------------------------------------------------------

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        metadata = self._metadata.metadata(exchange.provider.issuer)
        response = self._request_token(metadata, exchange)
        id_token = response.get("id_token")
        if not isinstance(id_token, str):
            raise InvalidIdTokenError
        claims = self._verify(metadata, exchange, id_token)
        access_token = response.get("access_token")
        if isinstance(access_token, str) and metadata.userinfo_endpoint:
            return {**self._userinfo(metadata, access_token, claims), **claims}
        return claims

    def _request_token(self, metadata: ProviderMetadata, exchange: CodeExchange) -> dict[str, Any]:
        provider = exchange.provider
        form = {
            "grant_type": "authorization_code",
            "code": exchange.code,
            "redirect_uri": provider.redirect_uri,
            "code_verifier": exchange.code_verifier,
            "client_id": provider.client_id,
        }
        if provider.credential.uses_private_key:
            # Authenticate with an assertion signed by the private key (ADR-0077 §1). Basic is not used.
            form.update(_assertion_fields(provider, metadata.token_endpoint))
            return self._post_form(metadata.token_endpoint, form, None)
        secret = provider.credential.secret
        if metadata.token_auth_methods and _BASIC_AUTH not in metadata.token_auth_methods:
            # For IdPs that don't accept Basic, send in the body (client_secret_post)
            form["client_secret"] = secret
            return self._post_form(metadata.token_endpoint, form, None)
        return self._post_form(metadata.token_endpoint, form, (provider.client_id, secret))

    def _decode(self, metadata: ProviderMetadata, token: str, **options: Any) -> dict[str, Any]:
        """Fetch the signing key and verify. **Key fetching happens in the same call** too.

        ⚠ **Don't move key fetching outside the caller's try.** Input broken as a JWT becomes
        ``jwt.DecodeError`` at key lookup. Moved outside, it escapes the verification net and
        becomes a 500 (an unauthenticated party can trigger it just by sending ``Bearer garbage``).
        """
        key = self._metadata.signing_key(metadata.jwks_uri, token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=list(metadata.signing_algorithms),
            # The issuer is the discovery document's (OidcMetadataCache checks it matches
            # where we fetched it from)
            issuer=metadata.issuer,
            **options,
        )
        return claims

    def _verify(self, metadata: ProviderMetadata, exchange: CodeExchange, id_token: str) -> dict[str, Any]:
        """Check signature, issuer, audience and ``nonce``.

        Skipping the ``nonce`` check leaves attacks that bring in an ID token obtained elsewhere
        (replay) unstopped.
        """
        try:
            claims = self._decode(metadata, id_token, audience=exchange.provider.client_id)
        except jwt.InvalidTokenError as error:
            logger.warning("sso_id_token_rejected")
            raise InvalidIdTokenError from error
        if claims.get("nonce") != exchange.nonce:
            logger.warning("sso_id_token_nonce_mismatch")
            raise InvalidIdTokenError
        return claims

    # ------------------------------------------------------------------
    # Logout propagation (ADR-0077 §3)
    # ------------------------------------------------------------------

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:
        """Verify ``logout_token`` as a JWT (signature, issuer, audience, expiry).

        ``exp`` and ``iat`` are **required**. The spec doesn't require ``exp``, but without it we
        can't tell "until when the notice is valid", and an intercepted notice could be replayed
        forever. Our own idp (assay) always includes both (ADR-0078 §3).
        """
        provider = verification.provider
        metadata = self._metadata.metadata(provider.issuer)
        try:
            return self._decode(
                metadata,
                verification.logout_token,
                audience=provider.client_id,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.InvalidTokenError as error:
            logger.warning("sso_logout_token_rejected")
            raise InvalidLogoutTokenError from error

    def _userinfo(self, metadata: ProviderMetadata, access_token: str, claims: Mapping[str, Any]) -> dict[str, Any]:
        """Fetch UserInfo to fill in. Login continues even if it can't be fetched.

        **Responses with a mismatched ``sub`` are discarded** (so nobody else's data overwrites it).
        """
        try:
            document = self._get_json(metadata.userinfo_endpoint, access_token)
        except IdentityProviderUnavailableError:
            logger.warning("sso_userinfo_unavailable")
            return {}
        return document if document.get("sub") == claims.get("sub") else {}

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post_form(self, url: str, form: Mapping[str, str], auth: tuple[str, str] | None) -> dict[str, Any]:
        try:
            response = httpx.post(
                url,
                data=dict(form),
                auth=auth,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return _as_document(response.json())
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("sso_token_request_failed")
            raise IdentityProviderUnavailableError from error

    def _get_json(self, url: str, access_token: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return _as_document(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityProviderUnavailableError from error


def _assertion_fields(provider: IdentityProvider, token_endpoint: str) -> dict[str, str]:
    """The two values ``private_key_jwt`` adds to the token request.

    ``aud`` is the token endpoint URL. idp accepts both ``<issuer>/token`` and
    ``<issuer>``, but using the value from discovery as is avoids
    mismatches.
    """
    assertion = build_client_assertion(
        ClientAssertionRequest(
            client_id=provider.client_id,
            audience=token_endpoint,
            credential=provider.credential,
        )
    )
    return {"client_assertion_type": ASSERTION_TYPE, "client_assertion": assertion}


def _as_document(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise IdentityProviderUnavailableError
    return payload


__all__ = ["HttpxOidcProviderGateway"]
