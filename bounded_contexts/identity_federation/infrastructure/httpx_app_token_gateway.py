"""``AppTokenGateway`` の実装（assay の discovery と JWKS を使う）。"""

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

#: assay のアクセストークンの ``typ``（RFC 9068）。ID トークンを持ち込ませないため確かめる。
_ACCESS_TOKEN_TYPE = "at+jwt"
#: アクセストークンは RS256 だけ（assay の実装）。対称鍵と ``none`` は入れない。
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
            # ⚠ 鍵の取得も try の中（壊れた入力が 500 に化けないように）
            key = self._metadata.signing_key(metadata.jwks_uri, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                issuer=metadata.issuer,
                # 人のログインのトークンの宛先は常にこれ（assay ADR-0042 決定 6）
                audience=f"{metadata.issuer}/userinfo",
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            logger.info("app_access_token_rejected")
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
