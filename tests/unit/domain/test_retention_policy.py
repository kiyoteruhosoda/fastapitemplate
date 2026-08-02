"""保持期間の境界（``0`` と負の日数は「削除しない」）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from bounded_contexts.audit.domain.value_objects.retention_policy import (
    LogRetentionPolicy,
)

_NOW = datetime(2026, 8, 2, 12, 0, 0)


def test_the_default_policy_deletes_nothing() -> None:
    """既定値だけでは 1 行も消えないこと（テンプレートが勝手に消し始めない）。"""
    policy = LogRetentionPolicy()

    assert policy.purges_nothing
    assert policy.application_log_cutoff(_NOW) is None
    assert policy.audit_log_cutoff(_NOW) is None


def test_a_positive_number_of_days_becomes_a_cutoff() -> None:
    policy = LogRetentionPolicy(application_log_days=30, audit_log_days=365)

    assert not policy.purges_nothing
    assert policy.application_log_cutoff(_NOW) == _NOW - timedelta(days=30)
    assert policy.audit_log_cutoff(_NOW) == _NOW - timedelta(days=365)


@pytest.mark.parametrize("days", [0, -1, -365])
def test_zero_or_negative_days_never_produce_a_cutoff(days: int) -> None:
    """打ち間違いで直近の行まで消えないこと（負の日数は未来の境界になる）。"""
    policy = LogRetentionPolicy(application_log_days=days, audit_log_days=days)

    assert policy.application_log_cutoff(_NOW) is None
    assert policy.audit_log_cutoff(_NOW) is None


def test_the_two_tables_are_kept_independently() -> None:
    """アプリログだけ消して監査ログは残す、という設定ができること。"""
    policy = LogRetentionPolicy(application_log_days=30)

    assert policy.application_log_cutoff(_NOW) == _NOW - timedelta(days=30)
    assert policy.audit_log_cutoff(_NOW) is None
    assert not policy.purges_nothing
