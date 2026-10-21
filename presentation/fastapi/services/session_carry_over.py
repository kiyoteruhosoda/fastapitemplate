"""新しいトークンが、前のセッションから引き継ぐもの。

トークンを出し直す経路（更新・ロールの切り替え・パスワードの変更）は、前のセッションの
**ロール**（ADR-0017）・**IdP のセッション**（ADR-0036）・**最後に実際にサインインした時刻**
（ADR-0060）を落とさずに渡す。1 つでも落とすと、そのトークンは別物になる
——IdP の停止が効かない・入り直さずに「入り直したばかり」になれる、など。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)


@dataclass(frozen=True)
class SessionCarryOver:
    """既定（何も渡さない）は「いま入口から入った」。"""

    active_role: str | None = None
    federated_login: FederatedLogin | None = None
    #: ``None`` は「いまサインインした」。渡してよいのは入口（パスワード・パスキー・SSO）だけ
    authenticated_at: datetime | None = None


#: 入口から入ったばかりのセッション
FRESH_SIGN_IN = SessionCarryOver()

__all__ = ["FRESH_SIGN_IN", "SessionCarryOver"]
