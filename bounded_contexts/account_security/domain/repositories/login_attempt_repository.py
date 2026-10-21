"""失敗の控えの永続化インターフェース（実装は Infrastructure 層）。

プロセスのメモリに置かないのは、Gunicorn が複数ワーカーで動くため
（ワーカーの数だけ試せてしまう）。WebAuthn のチャレンジと同じ理由（ADR-0058）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)


class LoginAttemptRepository(Protocol):
    def get(self, purpose: str, identifier: str) -> LoginAttempts:
        """控えを返す。無ければ空の控え（失敗 0 回）を返す。"""

    def save(self, attempts: LoginAttempts, now: datetime, policy: ThrottlePolicy) -> None:
        """控えを書く。**もう意味の無い行はこの機会に掃除する**（専用のジョブを持たない）。"""

    def forget(self, purpose: str, identifier: str) -> None:
        """控えを消す（正しく入れたとき）。"""


__all__ = ["LoginAttemptRepository"]
