"""Count, per user, "the authentication methods this app holds" (ADR-0076 §7).

This context answers **only for what it holds itself** — two-factor authentication (TOTP) and
passkeys. Passwords are a column of ``users``, so they belong to shared; IdP-based entry points
are answered by the identity federation context.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.domain.repositories.local_factor_directory import (
    LocalFactorDirectory,
)
from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)


@dataclass(frozen=True)
class CountLocalFactors:
    directory: LocalFactorDirectory

    def execute(self) -> dict[int, LocalFactors]:
        return self.directory.factors_by_user()

    def for_user(self, user_id: int) -> LocalFactors:
        """One user only. For when the target is fixed, such as one's own settings screen (ADR-0077 §5)."""
        return self.directory.factors_of(user_id)


__all__ = ["CountLocalFactors"]
