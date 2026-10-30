"""``MachineTokenGateway`` の実装（assay の discovery と JWKS を使う）。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import jwt

from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import OidcMetadataCache

logger = logging.getLogger(__name__)

#: 非対称鍵の署名だけ。対称鍵と ``none`` は入れない。
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]


class HttpxMachineTokenGateway:
    def __init__(self, *, metadata: OidcMetadataCache | None = None) -> None:
        self._metadata = metadata or OidcMetadataCache()

    def verify_machine_token(self, issuer: str, audience: str, token: str) -> Mapping[str, Any]:
        if not audience:
            # ⚠ 宛名を見ない検証はしない（別のアプリ宛てのトークンが通る。ADR-0082 §2 決定 4）
            raise InvalidMachineTokenError
        metadata = self._metadata.metadata(issuer)
        try:
            # ⚠ 鍵の取得も try の中（壊れた入力が 500 に化けないように）
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
