"""Implementation of ``MachineTokenGateway`` (uses assay's discovery and JWKS)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import jwt

from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import OidcMetadataCache

logger = logging.getLogger(__name__)

#: Asymmetric key signatures only. No symmetric keys and no ``none``.
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]


class HttpxMachineTokenGateway:
    def __init__(self, *, metadata: OidcMetadataCache | None = None) -> None:
        self._metadata = metadata or OidcMetadataCache()

    def verify_machine_token(self, issuer: str, audience: str, token: str) -> Mapping[str, Any]:
        if not audience:
            # ⚠ Never verify without checking the audience (tokens for other apps would pass. ADR-0082 §2 decision 4)
            raise InvalidMachineTokenError
        metadata = self._metadata.metadata(issuer)
        try:
            # ⚠ Key fetching is inside the try too (so broken input doesn't turn into a 500)
            key = self._metadata.signing_key(metadata.jwks_uri, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                issuer=metadata.issuer,
                audience=audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            logger.info("machine_token_rejected", extra={"reason": type(error).__name__})
            raise InvalidMachineTokenError from error
        return claims


__all__ = ["HttpxMachineTokenGateway"]
