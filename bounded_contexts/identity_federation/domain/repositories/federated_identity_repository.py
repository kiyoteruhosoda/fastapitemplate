"""Persistence interface for IdP account bindings (implemented in Infrastructure)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)


class FederatedIdentityRepository(Protocol):
    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        """Look up a binding. ``None`` if absent."""

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        """Save a binding (the same ``(issuer, subject)`` is not overwritten)."""

    def find_for_user(self, issuer: str, user_id: int) -> FederatedIdentity | None:
        """Look up whether that user is bound to that IdP (ADR-0077 §5)."""

    def unlink(self, identity: FederatedIdentity) -> None:
        """Delete the binding. **The user itself is not touched.**"""

    def touch(self, identity: FederatedIdentity) -> None:
        """Update the last login time (for inventory, and as the revocation address in reconciliation. ADR-0077 §7)."""

    def list_for_issuer(self, issuer: str) -> Sequence[FederatedIdentity]:
        """Return all users bound to that IdP (periodic reconciliation. ADR-0077 §7).

        ⚠ **No paging.** Reconciliation "asks about every `sub` we hold", so cutting it short would
        leave **the cut-off part unchecked every time**.
        """


__all__ = ["FederatedIdentityRepository"]
