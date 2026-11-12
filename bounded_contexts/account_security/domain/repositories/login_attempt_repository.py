"""Persistence interface for the failure records (implemented in Infrastructure).

Not kept in process memory because Gunicorn runs multiple workers (that would allow as many
tries as there are workers). Same reason as the WebAuthn challenges (ADR-0076 §9).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)


class LoginAttemptRepository(Protocol):
    def get(self, purpose: str, identifier: str) -> LoginAttempts:
        """Return the record. If there is none, return an empty record (0 failures)."""

    def save(self, attempts: LoginAttempts, now: datetime, policy: ThrottlePolicy) -> None:
        """Write the record. **Rows that no longer matter are cleaned up at the same time** (no dedicated job)."""

    def forget(self, purpose: str, identifier: str) -> None:
        """Delete the record (on a correct entry)."""


__all__ = ["LoginAttemptRepository"]
