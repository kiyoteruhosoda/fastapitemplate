"""失敗の数え上げと断り方（ADR-0058）。

いちばん確かめたいのは、**窓の外の失敗は数え直すこと**と、**断りは時間で解ける
こと**、そして**正しく入れたら忘れること**。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from bounded_contexts.account_security.domain.entities.login_attempts import (
    PURPOSE_LOGIN,
    LoginAttempts,
    ThrottlePolicy,
)

NOW = datetime(2026, 10, 21, 12, 0, 0)
POLICY = ThrottlePolicy(max_failures=3, window=timedelta(minutes=15), lock_duration=timedelta(minutes=10))


def _fresh() -> LoginAttempts:
    return LoginAttempts(purpose=PURPOSE_LOGIN, identifier="someone@example.com")


def _fail(times: int, start: datetime = NOW, step: timedelta = timedelta(seconds=10)) -> LoginAttempts:
    attempts = _fresh()
    for index in range(times):
        attempts = attempts.after_failure(start + step * index, POLICY)
    return attempts


def test_nothing_is_refused_before_the_limit() -> None:
    assert _fail(2).retry_after(NOW + timedelta(seconds=30)) is None


def test_reaching_the_limit_refuses_for_the_lock_duration() -> None:
    locked = _fail(3)
    locked_at = NOW + timedelta(seconds=20)

    assert locked.retry_after(locked_at) == timedelta(minutes=10)
    assert locked.retry_after(locked_at + timedelta(minutes=9)) == timedelta(minutes=1)
    # 時間で解ける。管理者の手は要らない
    assert locked.retry_after(locked_at + timedelta(minutes=10)) is None


def test_failures_outside_the_window_are_counted_afresh() -> None:
    # 2 回失敗して 20 分後に 1 回。窓（15 分）を過ぎているので 1 回目として数える
    attempts = _fail(2).after_failure(NOW + timedelta(minutes=20), POLICY)

    assert attempts.failures == 1
    assert attempts.window_started_at == NOW + timedelta(minutes=20)
    assert attempts.locked_until is None


def test_success_forgets_everything() -> None:
    cleared = _fail(3).after_success()

    assert cleared.failures == 0
    assert cleared.locked_until is None
    assert cleared.retry_after(NOW) is None


def test_a_disabled_policy_never_counts() -> None:
    assert ThrottlePolicy(max_failures=0, window=POLICY.window, lock_duration=POLICY.lock_duration).enabled is False
    assert POLICY.enabled is True


def test_stale_rows_are_those_past_both_the_window_and_the_lock() -> None:
    locked = _fail(3)
    # 断っているあいだは消さない
    assert locked.is_stale(NOW + timedelta(minutes=5), POLICY) is False
    # 断りも窓も過ぎたら消してよい
    assert locked.is_stale(NOW + timedelta(minutes=30), POLICY) is True
    # 窓の中の失敗は残す
    assert _fail(1).is_stale(NOW + timedelta(minutes=5), POLICY) is False
    assert _fresh().is_stale(NOW, POLICY) is True
