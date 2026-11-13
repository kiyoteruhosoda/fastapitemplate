"""Implementation of ``DpopProofVerifier`` (PyJWT. ADR-0103).

Performs the same checks as assay's ``domain::dpop``:

- ``typ`` is ``dpop+jwt``, ``alg`` is ES256 only (P-256 keys in Android Keystore)
- ``jwk`` is a P-256 public key only. Anything containing the private value (``d``) is refused
- The signature verifies with ``jwk``
- ``htm`` exactly matches the uppercase method; ``htu`` is compared with query and fragment removed
- ``iat`` from 120 s before now to 60 s after
- ``ath`` is the base64url of the access token's SHA-256
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import jwt

from bounded_contexts.identity_federation.domain.exceptions import DpopProofRejectedError
from bounded_contexts.identity_federation.domain.value_objects.dpop_proof import (
    MAX_CLOCK_AHEAD,
    MAX_PROOF_AGE,
    DpopProofRequirements,
    VerifiedDpopProof,
)

logger = logging.getLogger(__name__)

_PROOF_TYPE = "dpop+jwt"
_MAX_JTI_LENGTH = 256


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def jwk_thumbprint(x: str, y: str) -> str:
    """JWK Thumbprint of a P-256 public key (RFC 7638: SHA-256 of JSON with the required members in
    lexicographic order, no whitespace)."""
    canonical = json.dumps({"crv": "P-256", "kty": "EC", "x": x, "y": y}, separators=(",", ":"), sort_keys=True)
    return _b64url(hashlib.sha256(canonical.encode()).digest())


def access_token_hash(access_token: str) -> str:
    """``ath`` (RFC 9449 §4.2)."""
    return _b64url(hashlib.sha256(access_token.encode()).digest())


def _comparable_uri(uri: str) -> str | None:
    parts = urlsplit(uri)
    if parts.scheme.lower() not in {"https", "http"} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", ""))


def _public_p256(jwk: Any) -> tuple[str, str]:
    """Extract ``x`` and ``y`` from ``jwk``. Refuse unless it's a P-256 public key."""
    if not isinstance(jwk, dict) or "d" in jwk:
        raise DpopProofRejectedError
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise DpopProofRejectedError
    x, y = jwk.get("x"), jwk.get("y")
    if not isinstance(x, str) or not isinstance(y, str):
        raise DpopProofRejectedError
    try:
        # Also check they decode back to 32 bytes (the values go into the thumbprint JSON as is)
        if len(_b64url_decode(x)) != 32 or len(_b64url_decode(y)) != 32:
            raise DpopProofRejectedError
    except ValueError as error:
        raise DpopProofRejectedError from error
    return x, y


class PyJwtDpopProofVerifier:
    def verify(self, proof: str, requirements: DpopProofRequirements) -> VerifiedDpopProof:
        try:
            header = jwt.get_unverified_header(proof)
        except jwt.InvalidTokenError as error:
            raise DpopProofRejectedError from error
        if str(header.get("typ", "")).lower() != _PROOF_TYPE or header.get("alg") != "ES256":
            raise DpopProofRejectedError
        x, y = _public_p256(header.get("jwk"))
        claims = self._signed_claims(proof, x, y)
        jti = self._checked_jti(claims)
        issued_at = self._checked_issued_at(claims, requirements.now)
        if claims.get("htm") != requirements.method:
            raise DpopProofRejectedError
        presented_uri = claims.get("htu")
        expected_uri = _comparable_uri(requirements.uri)
        if not isinstance(presented_uri, str) or expected_uri is None:
            raise DpopProofRejectedError
        if _comparable_uri(presented_uri) != expected_uri:
            raise DpopProofRejectedError
        if claims.get("ath") != access_token_hash(requirements.access_token):
            raise DpopProofRejectedError
        return VerifiedDpopProof(jkt=jwk_thumbprint(x, y), jti=jti, issued_at=issued_at)

    @staticmethod
    def _signed_claims(proof: str, x: str, y: str) -> dict[str, Any]:
        try:
            key = jwt.PyJWK({"kty": "EC", "crv": "P-256", "x": x, "y": y}, algorithm="ES256")
            claims: dict[str, Any] = jwt.decode(
                proof,
                key,
                algorithms=["ES256"],
                options={"verify_aud": False, "verify_iat": False, "verify_exp": False, "require": []},
            )
        except (jwt.InvalidTokenError, jwt.PyJWKError) as error:
            logger.info("dpop_proof_signature_rejected")
            raise DpopProofRejectedError from error
        return claims

    @staticmethod
    def _checked_jti(claims: dict[str, Any]) -> str:
        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti or len(jti) > _MAX_JTI_LENGTH:
            raise DpopProofRejectedError
        return jti

    @staticmethod
    def _checked_issued_at(claims: dict[str, Any], now: datetime) -> datetime:
        iat = claims.get("iat")
        if not isinstance(iat, int) or isinstance(iat, bool):
            raise DpopProofRejectedError
        try:
            issued_at = datetime.fromtimestamp(iat, tz=UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise DpopProofRejectedError from error
        if issued_at < now - MAX_PROOF_AGE or issued_at > now + MAX_CLOCK_AHEAD:
            logger.info("dpop_proof_outside_the_window")
            raise DpopProofRejectedError
        return issued_at


__all__ = ["PyJwtDpopProofVerifier", "access_token_hash", "jwk_thumbprint"]
