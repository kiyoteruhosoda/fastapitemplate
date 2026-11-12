"""Check whether a presented token belongs to a stopped session (ADR-0077 §3).

Called every time by the token verifier (``TokenService``). **Tokens issued by a local login
carry no IdP session**, so in that case the result is always "valid"
— logout propagation can only end sessions that started via the IdP.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)


@dataclass(frozen=True)
class CheckSessionRevocation:
    revocations: SessionRevocationRepository

    def execute(self, login: FederatedLogin | None) -> bool:
        """``True`` if stopped. Anything without material to judge is ``False`` (valid)."""
        if login is None:
            return False
        return self.revocations.is_revoked(login)


__all__ = ["CheckSessionRevocation"]
