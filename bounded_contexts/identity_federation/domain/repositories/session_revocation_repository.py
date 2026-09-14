"""停止の記録の永続化インターフェース（実装は Infrastructure 層）。"""

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
        """記録を残す。**同じ ``jti`` が既にあれば何もせず ``False``**。

        ADR-0024 の送り手は再送のたびに同じ ``jti`` を使うので、ここが重複配送の
        受け止め口になる。期限切れの記録はこの機会に掃除する。
        """

    def is_revoked(self, login: FederatedLogin) -> bool:
        """そのログインが、届いた停止のどれかに当たるかどうか。"""


__all__ = ["SessionRevocationRepository"]
