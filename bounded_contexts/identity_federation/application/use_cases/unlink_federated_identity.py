"""Unlinking — the user removes their own binding to the IdP (ADR-0077 §5).

⚠ **Don't create users who can't sign in after removal.** Removing the IdP from someone with
neither a local password nor a passkey leaves only recovery by an administrator. Whether a
way in remains is **counted and passed in by the caller** — second factors live in another
context (``account_security``), and we don't reach across the boundary to fetch them
(same construction as ADR-0076 §7).
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoIdentityNotLinkedError,
    SsoLastEntranceError,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)


@dataclass(frozen=True)
class UnlinkFederatedIdentity:
    identities: FederatedIdentityRepository

    def execute(self, *, issuer: str, user_id: int, has_other_entrance: bool) -> None:
        identity = self.identities.find_for_user(issuer, user_id)
        if identity is None:
            raise SsoIdentityNotLinkedError
        if not has_other_entrance:
            raise SsoLastEntranceError
        self.identities.unlink(identity)


__all__ = ["UnlinkFederatedIdentity"]
