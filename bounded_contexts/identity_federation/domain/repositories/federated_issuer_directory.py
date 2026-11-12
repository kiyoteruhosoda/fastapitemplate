"""Interface for the binding inventory (implemented in Infrastructure. ADR-0076 §7)."""

from __future__ import annotations

from typing import Protocol


class FederatedIssuerDirectory(Protocol):
    def issuers_by_user(self) -> dict[int, tuple[str, ...]]:
        """User ID -> list of bound issuers. Users without bindings are omitted.

        ⚠ **Returns everyone at once.** A per-user lookup would make the screen query once per
        user.
        """


__all__ = ["FederatedIssuerDirectory"]
