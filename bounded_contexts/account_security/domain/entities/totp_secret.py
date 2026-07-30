"""TOTP シークレット（時刻ベース・ワンタイムパスワードの共有鍵）。

ユーザー 1 人につき 1 つ。``confirmed_at`` が入って初めて二要素認証が
「有効」になる。登録操作の途中（QR を表示しただけ）で有効化してしまうと、
認証アプリへの登録に失敗した利用者がログインできなくなるため、確認コードの
検証に成功するまでは未確認のまま保持する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TotpSecret:
    user_id: int
    secret: str
    confirmed_at: datetime | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


__all__ = ["TotpSecret"]
