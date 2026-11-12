"""The "link status of this user" shown on the settings screen (ADR-0077 §5).

Answers **only for oneself**; other users' bindings are not visible.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import (
    FederatedLinkDto,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)


@dataclass(frozen=True)
class DescribeFederatedLink:
    identities: FederatedIdentityRepository
    provider: IdentityProvider | None

    def execute(self, *, user_id: int) -> FederatedLinkDto:
        if self.provider is None:
            # If SSO is disabled, the screen hides this whole section.
            return FederatedLinkDto(available=False)
        identity = self.identities.find_for_user(self.provider.issuer, user_id)
        return FederatedLinkDto(
            available=True,
            display_name=self.provider.display_name,
            linked=identity is not None,
            linked_at=identity.linked_at if identity is not None else None,
        )


__all__ = ["DescribeFederatedLink"]
