"""List per user "which IdPs they are bound to" (ADR-0076 §7).

The IdP-side row of the "ways in" list. ⚠ **Having a binding = being able to sign in**
— even if the local password is taken away, as long as this row remains SSO sign-in works.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.repositories.federated_issuer_directory import (
    FederatedIssuerDirectory,
)


@dataclass(frozen=True)
class ListFederatedIssuers:
    directory: FederatedIssuerDirectory

    def execute(self) -> dict[int, tuple[str, ...]]:
        return self.directory.issuers_by_user()


__all__ = ["ListFederatedIssuers"]
