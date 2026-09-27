"""IdP アカウントとの結び付きの永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)


class FederatedIdentityRepository(Protocol):
    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        """結び付きを引く。無ければ ``None``。"""

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        """結び付きを保存する（同じ ``(issuer, subject)`` は上書きしない）。"""

    def find_for_user(self, issuer: str, user_id: int) -> FederatedIdentity | None:
        """その利用者が、その IdP と結び付いているかを引く（ADR-0040）。"""

    def unlink(self, identity: FederatedIdentity) -> None:
        """結び付きを消す。**利用者そのものには触らない。**"""

    def touch(self, identity: FederatedIdentity) -> None:
        """最終ログイン日時を更新する（棚卸しと、定期照合の失効の宛名。ADR-0043）。"""

    def list_for_issuer(self, issuer: str) -> Sequence[FederatedIdentity]:
        """その IdP と結び付いている利用者を全件返す（定期照合。ADR-0043）。

        ⚠ **ページングを持たない。** 照合は「こちらが持っている `sub` を全部聞く」
        ものなので、途中で切ると**切られたぶんが毎回確かめられないまま残る**。
        """


__all__ = ["FederatedIdentityRepository"]
