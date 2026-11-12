"""Gateway to users (``users``).

From identity federation's view, creating, finding and reassigning roles of users is "an
outside mechanism". So that Domain doesn't touch SQLAlchemy models, only the needed operations
are declared here, and the implementation (Infrastructure) bridges to the ``shared`` models.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.federated_account import (
    FederatedAccount,
    NewFederatedAccount,
)


class FederatedUserDirectory(Protocol):
    def find_by_id(self, user_id: int) -> FederatedAccount | None:
        """Look up a user by internal ID. ``None`` if absent."""

    def find_by_email(self, email: str) -> FederatedAccount | None:
        """Look up a user by email (the clue for the first binding)."""

    def provision(self, account: NewFederatedAccount) -> FederatedAccount:
        """Create a user. Must be created in a state that can't sign in with a password."""

    def refresh_profile(self, user_id: int, *, email: str | None, username: str) -> None:
        """Overwrite the copy with the name and email the IdP claimed (ADR-0077 §6).

        ⚠ **The copy treats the IdP as the source of truth** (idp ADR-0049 I5). Without writing,
        renames and email changes over there would leave **our display stale forever**.

        ⚠ **Don't write values that conflict with other users.** ``users.email`` is unique, so
        writing a conflicting value **makes the login fail with a 500** — a copy update must not
        break login, so only that field is silently skipped.
        """

    def apply_roles(self, user_id: int, roles: Sequence[str]) -> FederatedAccount:
        """Reassign roles (when operating with the IdP as source of truth).

        Unknown role names are silently dropped (so login doesn't stop when groups increase
        on the IdP side).
        """


__all__ = ["FederatedUserDirectory"]
