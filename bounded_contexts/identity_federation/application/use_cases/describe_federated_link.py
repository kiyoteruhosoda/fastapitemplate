"""設定画面に出す「この利用者の連携の状態」（ADR-0040）。

答えるのは**自分の分だけ**で、他人の結び付きは見えない。
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
            # SSO が無効なら、画面にはこの区画そのものを出さない。
            return FederatedLinkDto(available=False)
        identity = self.identities.find_for_user(self.provider.issuer, user_id)
        return FederatedLinkDto(
            available=True,
            display_name=self.provider.display_name,
            linked=identity is not None,
            linked_at=identity.linked_at if identity is not None else None,
        )


__all__ = ["DescribeFederatedLink"]
