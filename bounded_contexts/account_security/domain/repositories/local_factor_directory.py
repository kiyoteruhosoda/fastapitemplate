"""Interface for the second-factor inventory (implemented in Infrastructure; ADR-0076 §7)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)


class LocalFactorDirectory(Protocol):
    def factors_by_user(self) -> dict[int, LocalFactors]:
        """User ID → second factors. Users with none are not included.

        ⚠ **Returns everyone at once.** Looking them up one by one would make the screen
        query once per user.
        """

    def factors_of(self, user_id: int) -> LocalFactors:
        """Count for one user only. **Use only when the target is known to be a single person,
        such as one's own settings screen** (never call it from a list).
        """


__all__ = ["LocalFactorDirectory"]
