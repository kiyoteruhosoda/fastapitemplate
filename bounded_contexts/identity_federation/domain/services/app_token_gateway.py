"""Endpoint for reading assay access tokens coming from apps (ADR-0081 §1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class AppTokenGateway(Protocol):
    def verify_access_token(self, issuer: str, token: str) -> Mapping[str, Any]:
        """Check signature, ``typ``, issuer, audience (``{issuer}/userinfo``) and expiry, and return the claims.

        On mismatch ``AppAccessTokenRejectedError``; if the IdP is unreachable,
        ``IdentityProviderUnavailableError``.
        """
        ...

    def verify_id_token(self, issuer: str, id_token: str, client_ids: frozenset[str]) -> Mapping[str, Any]:
        """Check the signature, issuer, audience (any of ``client_ids``) and expiry of the ID token sent by
        the app (ADR-0103).

        With a bound token (``cnf.jkt``) we can't fetch userinfo ourselves, so the profile of a first-time
        person is read from here. On mismatch ``AppAccessTokenRejectedError``.
        """
        ...

    def userinfo(self, issuer: str, token: str) -> Mapping[str, Any]:
        """Fetch userinfo with that token. A response with a mismatched ``sub`` is returned as empty."""
        ...


__all__ = ["AppTokenGateway"]
