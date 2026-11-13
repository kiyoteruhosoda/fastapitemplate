"""Fetching and caching OpenID Provider metadata (endpoints and signing keys).

- **Endpoints come from discovery** (``<issuer>/.well-known/openid-configuration``).
    Configuring each URL separately couldn't follow IdP-side changes and adds more settings.
- **Signing keys come from JWKS**. Keys rotate, so they are also held in a form that can be
    refetched as needed (``PyJWKClient`` caches and refetches internally).
- **Outgoing requests identify themselves by name** (``USER_AGENT``). With the default, the
    IdP's front end may drop them (see below).

Fetching both on every login would add two round trips to the IdP, so a short-TTL cache sits
in between. It is per process; stale values last only for the TTL.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from shared.kernel.version import load_build_info, project_name

# Accepted ID token signature algorithms. **No symmetric keys (HS*) and no ``none``**
# — HS* uses the client secret as the key, so parties other than the IdP could sign.
ALLOWED_SIGNING_ALGORITHMS: tuple[str, ...] = (
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
)

_DISCOVERY_PATH = "/.well-known/openid-configuration"
_CACHE_TTL_SECONDS = 300.0

# Interval (per issuer) at which JWKS may be refetched when a ``kid`` not in the local keys arrives.
# Kept short so that right after a key rotation we **don't keep rejecting the new key**.
_JWKS_REFRESH_INTERVAL_SECONDS = 60.0

# Name that requests to the IdP identify themselves with. **Don't leave it to the default UA.**
# Only JWKS is fetched by PyJWT (``PyJWKClient``) via its internal urllib, so by default it
# identifies as ``Python-urllib/3.x``. CDNs / WAFs in front of the IdP may drop this UA
# (Cloudflare actually returned 403 and only the login callback failed): discovery and token
# exchange pass but only ID token verification fails.
#
# ⚠ **Don't hard-code the name.** Derive it from the app's own name (``[project].name`` in
# ``pyproject.toml``) (ADR-0073 §2). Hard-coded, apps created from the template
# **keep identifying as another app** — which is actually what happened for a long time.
USER_AGENT = f"{project_name()}/{load_build_info().version}"


@dataclass(frozen=True)
class ProviderMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str = ""
    #: RP-Initiated Logout endpoint. **Optional** — some IdPs don't publish it, so discovery
    #: still succeeds without it (only the sign-out feature becomes unavailable).
    end_session_endpoint: str = ""
    signing_algorithms: tuple[str, ...] = ()
    token_auth_methods: tuple[str, ...] = ()

    @classmethod
    def of(cls, document: dict[str, Any]) -> ProviderMetadata:
        """Extract only the needed fields from the discovery document.

        A response missing any of authorization, token or JWKS is not a valid OpenID Provider
        (this also catches HTML returned because of a mistyped IdP URL).
        """
        metadata = cls(
            issuer=_text(document.get("issuer")),
            authorization_endpoint=_text(document.get("authorization_endpoint")),
            token_endpoint=_text(document.get("token_endpoint")),
            jwks_uri=_text(document.get("jwks_uri")),
            userinfo_endpoint=_text(document.get("userinfo_endpoint")),
            end_session_endpoint=_text(document.get("end_session_endpoint")),
            signing_algorithms=_supported_algorithms(document.get("id_token_signing_alg_values_supported")),
            token_auth_methods=tuple(_texts(document.get("token_endpoint_auth_methods_supported"))),
        )
        if not (metadata.authorization_endpoint and metadata.token_endpoint and metadata.jwks_uri):
            raise IdentityProviderUnavailableError
        return metadata


class OidcMetadataCache:
    """TTL cache of discovery documents and JWKS clients (in-process)."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._documents: dict[str, tuple[float, ProviderMetadata]] = {}
        self._jwks: dict[str, jwt.PyJWKClient] = {}
        #: jwks_uri -> time JWKS was last refetched. See ``signing_key`` below.
        self._jwks_refreshed_at: dict[str, float] = {}

    def metadata(self, issuer: str) -> ProviderMetadata:
        with self._lock:
            cached = self._documents.get(issuer)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
        metadata = ProviderMetadata.of(self._fetch(f"{issuer.rstrip('/')}{_DISCOVERY_PATH}"))
        _require_same_issuer(metadata, issuer)
        with self._lock:
            self._documents[issuer] = (time.monotonic() + _CACHE_TTL_SECONDS, metadata)
        return metadata

    def signing_key(self, jwks_uri: str, token: str) -> Any:
        """Return the public key matching the token's ``kid``.

        ⚠ **Call this only from inside a try that catches ``jwt.InvalidTokenError``.** Input that
        is broken as a JWT becomes ``jwt.DecodeError`` here. Called outside, that exception escapes
        the verification net and turns into a 500 (triggerable just by sending ``Bearer garbage``).

        ⚠ **JWKS refetches are spaced per issuer.** Left to ``PyJWKClient``, it refetches every time
        a ``kid`` is not found. The machine endpoint (ADR-0076 §10) is where an unauthenticated party
        **can throw in tokens with any ``kid``**, making "1 request = 1 round trip to idp" and an
        amplification springboard. Not remembering per ``kid`` because that doesn't work against a
        party that keeps changing ``kid`` (the memo can be flooded too). Throttling refetches
        **per issuer** keeps it to one round trip per interval no matter how many ``kid`` values come.

        ⚠ **Separate "no such key" from "JWKS unusable".** The former is a wrong token (the caller
        returns 401); the latter is an upstream fault (502) — not only unreachable, but also non-JSON,
        no keys at all, or unreadable keys count as the latter.
        Making it look like a token error makes legitimate callers doubt their own credentials.
        """
        kid = _unverified_kid(token)
        if kid is None:
            # ``PyJWKClient`` only considers keys that have a ``kid``, so a token without ``kid``
            # can't be matched anyway. Refuse without fetching.
            raise jwt.DecodeError("token has no kid")
        client = self._jwks_client(jwks_uri)
        try:
            key = jwt.PyJWKClient.match_kid(client.get_signing_keys(), kid)
            if key is None and self._may_refresh(jwks_uri):
                key = jwt.PyJWKClient.match_kid(client.get_signing_keys(refresh=True), kid)
        except (jwt.PyJWTError, ValueError) as error:
            # Unreachable (``PyJWKClientConnectionError``) and reachable-but-unusable
            # (``PyJWKClientError`` / ``PyJWKSetError`` / not JSON) are both upstream faults.
            raise IdentityProviderUnavailableError from error
        if key is None:
            raise jwt.DecodeError(f"no signing key for kid {kid}")
        return key.key

    def _jwks_client(self, jwks_uri: str) -> jwt.PyJWKClient:
        with self._lock:
            client = self._jwks.get(jwks_uri)
            if client is None:
                client = self._new_jwks_client(jwks_uri)
                self._jwks[jwks_uri] = client
        return client

    def _new_jwks_client(self, jwks_uri: str) -> jwt.PyJWKClient:
        try:
            return jwt.PyJWKClient(
                jwks_uri,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
        except jwt.PyJWKClientError as error:
            # The discovery document claims a ``jwks_uri`` that is not http(s) (IdP-side defect).
            raise IdentityProviderUnavailableError from error

    def _may_refresh(self, jwks_uri: str) -> bool:
        """If a refetch is allowed, take the slot and return true (taken before fetching, so
        concurrent requests don't overlap)."""
        with self._lock:
            now = time.monotonic()
            last = self._jwks_refreshed_at.get(jwks_uri)
            if last is not None and now - last < _JWKS_REFRESH_INTERVAL_SECONDS:
                return False
            self._jwks_refreshed_at[jwks_uri] = now
            return True

    def _fetch(self, url: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
                # ⚠ Don't follow redirects (ADR-0090). The issuer check only applies to the first URL.
                follow_redirects=False,
            )
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityProviderUnavailableError from error
        if not isinstance(document, dict):
            raise IdentityProviderUnavailableError
        return document


def _unverified_kid(token: str) -> str | None:
    """Read only the header's ``kid`` without verifying the signature. ``None`` if missing or not a string."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    return kid if isinstance(kid, str) and kid else None


def _require_same_issuer(metadata: ProviderMetadata, issuer: str) -> None:
    """Check that the ``issuer`` claimed by the discovery document equals where we fetched it from.

    OpenID Connect Discovery requires them to match. Fetching follows redirects
    (``follow_redirects``), so without this check, if handed another issuer's document we would
    accept ID tokens signed by that issuer as is.
    Only a trailing ``/`` difference is tolerated (the settings side strips it).
    """
    if metadata.issuer.rstrip("/") != issuer.rstrip("/"):
        raise IdentityProviderUnavailableError


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_text(item) for item in value if _text(item))


def _supported_algorithms(value: object) -> tuple[str, ...]:
    """Keep only the algorithms the IdP advertises that we accept.

    If none are advertised, use ``RS256``, which OpenID Connect makes mandatory.
    """
    advertised = _texts(value)
    allowed = tuple(algorithm for algorithm in advertised if algorithm in ALLOWED_SIGNING_ALGORITHMS)
    return allowed or ("RS256",)


__all__ = ["ALLOWED_SIGNING_ALGORITHMS", "OidcMetadataCache", "ProviderMetadata"]
