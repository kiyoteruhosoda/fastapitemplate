"""連携の解除 ——利用者が自分で IdP との結び付きを外す（ADR-0040）。

⚠ **外したあと入れなくなる利用者を作らない。** ローカルのパスワードもパスキーも
無い相手から IdP を外すと、残るのは管理者による復旧だけになる。残る入り口が
あるかどうかは**呼び出し側が数えて渡す** ——第二要素を持っているのは別の
コンテキスト（``account_security``）で、境界を越えて引きに行かないため
（ADR-0039 と同じ組み立て方）。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoIdentityNotLinkedError,
    SsoLastEntranceError,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)


@dataclass(frozen=True)
class UnlinkFederatedIdentity:
    identities: FederatedIdentityRepository

    def execute(self, *, issuer: str, user_id: int, has_other_entrance: bool) -> None:
        identity = self.identities.find_for_user(issuer, user_id)
        if identity is None:
            raise SsoIdentityNotLinkedError
        if not has_other_entrance:
            raise SsoLastEntranceError
        self.identities.unlink(identity)


__all__ = ["UnlinkFederatedIdentity"]
