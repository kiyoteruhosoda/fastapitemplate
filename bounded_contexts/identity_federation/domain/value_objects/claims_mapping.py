"""Mapping of ID token (and UserInfo) claims -> :class:`FederatedUser`.

Claim names differ per IdP, so they are configurable (``OIDC_*_CLAIM``). This only holds
"which name to read what from" and does no communication (a pure conversion, so unit
tests can verify it).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidIdTokenError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_user import (
    FederatedUser,
)

# Fallback when the display name isn't in the mapped claim. Absorbs IdP implementation differences.
_USERNAME_FALLBACK_CLAIMS = ("name", "preferred_username", "nickname")


@dataclass(frozen=True)
class ClaimsMapping:
    email_claim: str = "email"
    username_claim: str = "name"

    def apply(self, claims: Mapping[str, Any]) -> FederatedUser:
        """Map the claims to user information.

        Anything without ``sub`` is not a valid ID token.

        ⚠ **Passes even without an email** (ADR-0077 §6). The binding key is ``sub``, so already
        bound parties can sign in without an email. **Refuse where its absence matters**
        — when merging by email the first time, and when creating a user.
        """
        subject = _text(claims.get("sub"))
        if not subject:
            raise InvalidIdTokenError
        email = _text(claims.get(self.email_claim))
        return FederatedUser(
            subject=subject,
            email=email.lower() if email else None,
            username=self._username(claims, email, subject),
            email_verified=claims.get("email_verified") is True,
        )

    def _username(self, claims: Mapping[str, Any], email: str, subject: str) -> str:
        """Display name. If the mapped claim is empty, an alias claim; failing that, the email's local part.

        ⚠ **If there's no email either, use ``sub``.** It's hard to read, but **better than creating a
        user with an empty display name** — it can be fixed on screen later.
        """
        candidates = (self.username_claim, *_USERNAME_FALLBACK_CLAIMS)
        for claim in candidates:
            value = _text(claims.get(claim))
            if value:
                return value
        return email.partition("@")[0] if email else subject


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["ClaimsMapping"]
