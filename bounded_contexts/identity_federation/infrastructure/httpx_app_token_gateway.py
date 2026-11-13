"""Implementation of ``AppTokenGateway`` (uses assay's discovery and JWKS)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx
import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    AppAccessTokenRejectedError,
    IdentityProviderUnavailableError,
)
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import (
    USER_AGENT,
    OidcMetadataCache,
)

logger = logging.getLogger(__name__)

#: ``typ`` of assay access tokens (RFC 9068). Checked so ID tokens can't be smuggled in.
_ACCESS_TOKEN_TYPE = "at+jwt"
#: Access tokens are RS256 only (assay's implementation). No symmetric keys and no ``none``.
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]


class HttpxAppTokenGateway:
    def __init__(self, *, metadata: OidcMetadataCache | None = None, timeout_seconds: float = 10.0) -> None:
        self._metadata = metadata or OidcMetadataCache(timeout_seconds=timeout_seconds)
        self._timeout = timeout_seconds

    def verify_access_token(self, issuer: str, token: str) -> Mapping[str, Any]:
        metadata = self._metadata.metadata(issuer)
        try:
            if str(jwt.get_unverified_header(token).get("typ", "")).lower() != _ACCESS_TOKEN_TYPE:
                raise AppAccessTokenRejectedError
            # ⚠ Key fetching is inside the try too (so broken input doesn't turn into a 500)
            key = self._metadata.signing_key(metadata.jwks_uri, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                issuer=metadata.issuer,
                # The audience of human login tokens is always this (assay ADR-0042 decision 6)
                audience=f"{metadata.issuer}/userinfo",
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            logger.info("app_access_token_rejected")
            raise AppAccessTokenRejectedError from error
        return claims

    def verify_id_token(self, issuer: str, id_token: str, client_ids: frozenset[str]) -> Mapping[str, Any]:
        metadata = self._metadata.metadata(issuer)
        try:
            # ⚠ Key fetching is inside the try too (so broken input doesn't turn into a 500)
            key = self._metadata.signing_key(metadata.jwks_uri, id_token)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key,
                algorithms=_ALGORITHMS,
                issuer=metadata.issuer,
                # The audience is the app's client_id (the ID token's aud). Only apps we may accept
                audience=sorted(client_ids),
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            logger.info("app_id_token_rejected")
            raise AppAccessTokenRejectedError from error
        return claims

    def userinfo(self, issuer: str, token: str) -> Mapping[str, Any]:
        metadata = self._metadata.metadata(issuer)
        if not metadata.userinfo_endpoint:
            return {}
        try:
            response = httpx.get(
                metadata.userinfo_endpoint,
                headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityProviderUnavailableError from error
        if not isinstance(document, dict):
            return {}
        return document


__all__ = ["HttpxAppTokenGateway"]
