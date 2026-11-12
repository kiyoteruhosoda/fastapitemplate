"""Persistence interface for logout records (implemented in Infrastructure)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)


class SessionRevocationRepository(Protocol):
    def record(self, revocation: SessionRevocation) -> bool:
        """Store the record. **If the same ``jti`` already exists, do nothing and return ``False``**.

        The sender in ADR-0078 §3 uses the same ``jti`` on every resend, so this is where duplicate
        deliveries are absorbed. Expired records are cleaned up at this opportunity.
        """

    def is_revoked(self, login: FederatedLogin) -> bool:
        """Whether that login is hit by any of the received logouts."""


__all__ = ["SessionRevocationRepository"]
