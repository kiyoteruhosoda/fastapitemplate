"""IdP アカウントとの結び付きの永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)


class FederatedIdentityRepository(Protocol):
    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        """結び付きを引く。無ければ ``None``。"""

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        """結び付きを保存する（同じ ``(issuer, subject)`` は上書きしない）。"""

    def touch(self, identity: FederatedIdentity) -> None:
        """最終ログイン日時を更新する（棚卸しのため。認可には使わない）。"""


__all__ = ["FederatedIdentityRepository"]
