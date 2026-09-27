"""提示されたトークンが、停止済みのセッションのものかを見る（ADR-0036）。

トークンを検証する側（``TokenService``）から毎回呼ばれる。**ローカルのログインで
発行されたトークンには IdP のセッションが載っていない**ので、その場合は常に「有効」
——停止の伝播が消せるのは、IdP 経由で始まったセッションだけである。
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
        """停止済みなら ``True``。判断する材料が無いものは ``False``（有効）とする。"""
        if login is None:
            return False
        return self.revocations.is_revoked(login)


__all__ = ["CheckSessionRevocation"]
