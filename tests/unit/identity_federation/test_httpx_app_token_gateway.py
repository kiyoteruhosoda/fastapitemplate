"""アプリの assay のアクセストークンの検証（ADR-0045）。鍵は試験の中で作る。"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from bounded_contexts.identity_federation.domain.exceptions import AppAccessTokenRejectedError
from bounded_contexts.identity_federation.infrastructure.httpx_app_token_gateway import HttpxAppTokenGateway
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import OidcMetadataCache, ProviderMetadata

_ISSUER = "https://idp.example.test/tenant"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _Metadata(OidcMetadataCache):
    def metadata(self, issuer: str) -> ProviderMetadata:
        return ProviderMetadata(
            issuer=_ISSUER,
            authorization_endpoint=f"{_ISSUER}/authorize",
            token_endpoint=f"{_ISSUER}/token",
            jwks_uri=f"{_ISSUER}/.well-known/jwks.json",
        )

    def signing_key(self, jwks_uri: str, token: str) -> Any:
        jwt.get_unverified_header(token)  # 壊れた入力はここで DecodeError（本物と同じ）
        return _KEY.public_key()


def _token(key: rsa.RSAPrivateKey = _KEY, typ: str = "at+jwt", **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "sub": "u1",
        "aud": f"{_ISSUER}/userinfo",
        "client_id": "app",
        "iat": now,
        "exp": now + 300,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"typ": typ, "kid": "k1"})


@pytest.fixture
def gateway() -> HttpxAppTokenGateway:
    return HttpxAppTokenGateway(metadata=_Metadata())


def test_a_valid_access_token_is_read(gateway: HttpxAppTokenGateway) -> None:
    assert gateway.verify_access_token(_ISSUER, _token())["client_id"] == "app"


@pytest.mark.parametrize(
    "token",
    [
        _token(typ="JWT"),  # ID トークンを持ち込ませない
        _token(key=_OTHER_KEY),
        _token(iss="https://evil.example.test"),
        _token(aud="api://blobshare"),
        _token(exp=int(time.time()) - 10),
        "garbage",
    ],
)
def test_other_tokens_are_rejected(gateway: HttpxAppTokenGateway, token: str) -> None:
    with pytest.raises(AppAccessTokenRejectedError):
        gateway.verify_access_token(_ISSUER, token)
