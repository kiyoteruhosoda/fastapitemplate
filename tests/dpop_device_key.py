"""アプリの代わりに P-256 の鍵で DPoP の証明を作る（ADR-0103 の試験）。"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from bounded_contexts.identity_federation.infrastructure.pyjwt_dpop_proof_verifier import (
    access_token_hash,
    jwk_thumbprint,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class DeviceKey:
    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict[str, str]:
        numbers = self.private_key.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        }

    @property
    def thumbprint(self) -> str:
        return jwk_thumbprint(self.jwk["x"], self.jwk["y"])

    def proof(
        self,
        method: str,
        uri: str,
        access_token: str | None,
        *,
        iat: int | None = None,
        jti: str | None = None,
        header: dict[str, Any] | None = None,
    ) -> str:
        claims: dict[str, Any] = {
            "jti": jti or uuid.uuid4().hex,
            "htm": method,
            "htu": uri,
            "iat": int(time.time()) if iat is None else iat,
        }
        if access_token is not None:
            claims["ath"] = access_token_hash(access_token)
        headers = {"typ": "dpop+jwt", "jwk": self.jwk} if header is None else header
        return jwt.encode(claims, self.private_key, algorithm="ES256", headers=headers)


__all__ = ["DeviceKey"]
