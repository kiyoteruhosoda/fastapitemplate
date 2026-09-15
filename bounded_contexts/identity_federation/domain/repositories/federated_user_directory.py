"""利用者（``users``）への窓口。

ID 連携から見ると、利用者の作成・検索・ロールの付け替えは「外の仕組み」に当たる。
Domain 層が SQLAlchemy のモデルへ触れないよう、必要な操作だけをここで宣言し、
実装（Infrastructure 層）が ``shared`` のモデルへ橋渡しする。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.federated_account import (
    FederatedAccount,
    NewFederatedAccount,
)


class FederatedUserDirectory(Protocol):
    def find_by_id(self, user_id: int) -> FederatedAccount | None:
        """利用者を内部 ID で引く。無ければ ``None``。"""

    def find_by_email(self, email: str) -> FederatedAccount | None:
        """利用者をメールアドレスで引く（初回の結び付けの手掛かり）。"""

    def provision(self, account: NewFederatedAccount) -> FederatedAccount:
        """利用者を作る。パスワードでは入れない状態で作ること。"""

    def refresh_profile(self, user_id: int, *, email: str | None, username: str) -> None:
        """IdP が名乗った名前とメールアドレスを写しへ上書きする（ADR-0042）。

        ⚠ **写しは IdP を正とする**（idp の ADR-0049 I5）。書かないと、向こうで
        改名・メール変更をしても**こちらの表示は永久に古いまま**になる。

        ⚠ **他の利用者とぶつかる値は書かない。** ``users.email`` は一意なので、
        ぶつかったまま書くと**ログインが 500 で落ちる** ——写しの更新でログインを
        壊してはいけないので、その項目だけ黙って見送る。
        """

    def apply_roles(self, user_id: int, roles: Sequence[str]) -> FederatedAccount:
        """ロールを与え直す（IdP を正とする運用のとき）。

        存在しないロール名は黙って捨てる（IdP 側のグループが増えても
        ログインが止まらないようにする）。
        """


__all__ = ["FederatedUserDirectory"]
