"""宛名ごとの失敗の数え上げ（ADR-0076 §9）。

「窓の中で *N* 回失敗したら *L* のあいだ断る」を、**判定と状態の遷移だけ**で持つ。
いつが「いま」かは外から渡す。DB もリクエストも知らない。

数える単位は**送られてきた宛名**であって、実在するアカウントではない。
実在するものだけを数えると、断られるかどうかで存在が分かってしまう。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

# 用途。DB ネイティブ ENUM は使わない方針のため、許可値は Python 側で管理する。
PURPOSE_LOGIN = "login"
PURPOSE_PASSWORD_RESET = "password_reset"
ATTEMPT_PURPOSES: tuple[str, ...] = (PURPOSE_LOGIN, PURPOSE_PASSWORD_RESET)


@dataclass(frozen=True)
class ThrottlePolicy:
    """窓の中で何回まで許し、超えたらどれだけ断るか。

    ``max_failures`` が 0 なら**数えない**（開発の便宜。本番で 0 にしない）。
    """

    max_failures: int
    window: timedelta
    lock_duration: timedelta

    @property
    def enabled(self) -> bool:
        return self.max_failures > 0


@dataclass(frozen=True)
class LoginAttempts:
    """宛名 1 つ分の失敗の控え。

    *window_started_at* は数え始めた時刻。窓を過ぎた失敗は数え直す。
    *locked_until* が入っているあいだは断る。
    """

    purpose: str
    identifier: str
    failures: int = 0
    window_started_at: datetime | None = None
    locked_until: datetime | None = None

    def retry_after(self, now: datetime) -> timedelta | None:
        """断っているなら、あとどれだけ待つか。断っていなければ ``None``。"""
        if self.locked_until is None or now >= self.locked_until:
            return None
        return self.locked_until - now

    def after_failure(self, now: datetime, policy: ThrottlePolicy) -> LoginAttempts:
        """1 回失敗した。窓の外なら数え直し、上限に達したら断り始める。"""
        if self.window_started_at is None or now - self.window_started_at >= policy.window:
            failures, started = 1, now
        else:
            failures, started = self.failures + 1, self.window_started_at
        locked_until = now + policy.lock_duration if failures >= policy.max_failures else None
        return replace(self, failures=failures, window_started_at=started, locked_until=locked_until)

    def after_success(self) -> LoginAttempts:
        """正しく入れた。それまでの失敗は打ち間違いなので忘れる。"""
        return replace(self, failures=0, window_started_at=None, locked_until=None)

    def is_stale(self, now: datetime, policy: ThrottlePolicy) -> bool:
        """もう覚えておく意味が無い（窓も断りも過ぎた）。掃除の対象。"""
        if self.locked_until is not None and now < self.locked_until:
            return False
        return self.window_started_at is None or now - self.window_started_at >= policy.window


__all__ = [
    "ATTEMPT_PURPOSES",
    "PURPOSE_LOGIN",
    "PURPOSE_PASSWORD_RESET",
    "LoginAttempts",
    "ThrottlePolicy",
]
