"""コールバックが発行する 1 回限りの引き換え券。

IdP からの戻りはブラウザの**画面遷移**で、SPA の JavaScript は応答本文を読めない。
トークンを URL に載せると履歴・Referer・アクセスログへ残るため、代わりに短命の
引き換え券だけを渡し、SPA が ``POST /api/auth/sso/token`` でトークンへ交換する
（ADR-0025）。

券そのものは持ち主に渡す資格情報なので、DB にはハッシュだけを保存する
（パスワードリセットトークンと同じ扱い）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SsoLoginTicket:
    ticket_hash: str
    user_id: int
    redirect_to: str
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


__all__ = ["SsoLoginTicket"]
