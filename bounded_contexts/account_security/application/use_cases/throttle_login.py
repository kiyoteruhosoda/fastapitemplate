"""宛名ごとにログインの失敗を数え、上限を超えたらしばらく断る（ADR-0076 §9）。

使い方は 3 手。**試す前に** :meth:`require_allowed`、**数えるべき試行があったら**
:meth:`record_attempt`、**通ったら** :meth:`record_success`。

数える単位は送られてきた宛名で、実在するかは見ない。実在するものだけを数えると、
断られるかどうかで存在が分かってしまう。
"""

from __future__ import annotations

from datetime import datetime

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)
from bounded_contexts.account_security.domain.exceptions import TooManyAttemptsError
from bounded_contexts.account_security.domain.repositories.login_attempt_repository import (
    LoginAttemptRepository,
)


def normalize_identifier(identifier: str) -> str:
    """大文字小文字と前後の空白で別の宛名にならないようにする。"""
    return identifier.strip().lower()


class ThrottleLogin:
    def __init__(self, repository: LoginAttemptRepository, policy: ThrottlePolicy) -> None:
        self._repository = repository
        self._policy = policy

    def require_allowed(self, purpose: str, identifier: str, now: datetime) -> None:
        """断っている最中なら :class:`TooManyAttemptsError`。"""
        if not self._policy.enabled:
            return
        retry_after = self._load(purpose, identifier).retry_after(now)
        if retry_after is not None:
            raise TooManyAttemptsError(retry_after_seconds=max(int(retry_after.total_seconds()), 1))

    def record_attempt(self, purpose: str, identifier: str, now: datetime) -> bool:
        """1 回数える。**この 1 回で断り始めたなら** ``True``（監査に残すため）。

        ログインでは失敗を、再設定の要求では成功も数える（成功しても相手に
        メールが届くので、数えないと受信箱を埋められる）。
        """
        if not self._policy.enabled:
            return False
        before = self._load(purpose, identifier)
        after = before.after_failure(now, self._policy)
        self._repository.save(after, now, self._policy)
        return after.locked_until is not None and before.retry_after(now) is None

    def record_success(self, purpose: str, identifier: str) -> None:
        """正しく入れた。それまでの失敗は打ち間違いなので忘れる。"""
        if not self._policy.enabled:
            return
        self._repository.forget(purpose, normalize_identifier(identifier))

    def _load(self, purpose: str, identifier: str) -> LoginAttempts:
        return self._repository.get(purpose, normalize_identifier(identifier))


__all__ = ["ThrottleLogin", "normalize_identifier"]
