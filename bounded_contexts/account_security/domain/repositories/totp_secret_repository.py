"""TOTP シークレットの永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from bounded_contexts.account_security.domain.entities.totp_secret import TotpSecret


class TotpSecretRepository(Protocol):
    def find_by_user(self, user_id: int) -> TotpSecret | None:
        """*user_id* のシークレットを返す（未登録なら ``None``）。"""

    def save(self, secret: TotpSecret) -> TotpSecret:
        """新規登録または上書き保存する。"""

    def confirm(self, user_id: int, confirmed_at: datetime) -> TotpSecret:
        """登録を確認済みにする（二要素認証が有効になる）。"""

    def delete(self, user_id: int) -> None:
        """シークレットを削除する（二要素認証を無効化する）。"""


__all__ = ["TotpSecretRepository"]
