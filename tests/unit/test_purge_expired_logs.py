"""掃除のユースケース（何を呼ぶか・何を呼ばないか）。"""

from __future__ import annotations

from datetime import datetime, timedelta

from bounded_contexts.audit.application.use_cases.purge_expired_logs import (
    PurgeExpiredLogs,
)
from bounded_contexts.audit.domain.value_objects.retention_policy import (
    LogRetentionPolicy,
)

_NOW = datetime(2026, 8, 2, 12, 0, 0)


class _SpyRemover:
    """削除の依頼を記録するだけの差し替え（DB を触らない）。"""

    def __init__(self, application_logs: int = 0, audit_logs: int = 0) -> None:
        self.application_cutoffs: list[datetime] = []
        self.audit_cutoffs: list[datetime] = []
        self._application_logs = application_logs
        self._audit_logs = audit_logs

    def delete_application_logs_before(self, cutoff: datetime) -> int:
        self.application_cutoffs.append(cutoff)
        return self._application_logs

    def delete_audit_logs_before(self, cutoff: datetime) -> int:
        self.audit_cutoffs.append(cutoff)
        return self._audit_logs


def test_the_default_policy_does_not_touch_the_database() -> None:
    """既定（どちらも 0）なら削除を一切依頼しないこと。"""
    remover = _SpyRemover()

    outcome = PurgeExpiredLogs(remover).execute(LogRetentionPolicy(), _NOW)

    assert outcome.total == 0
    assert remover.application_cutoffs == []
    assert remover.audit_cutoffs == []


def test_each_table_is_purged_with_its_own_cutoff() -> None:
    remover = _SpyRemover(application_logs=12, audit_logs=3)

    outcome = PurgeExpiredLogs(remover).execute(LogRetentionPolicy(application_log_days=30, audit_log_days=365), _NOW)

    assert remover.application_cutoffs == [_NOW - timedelta(days=30)]
    assert remover.audit_cutoffs == [_NOW - timedelta(days=365)]
    assert (outcome.application_logs, outcome.audit_logs, outcome.total) == (12, 3, 15)


def test_the_audit_log_is_left_alone_when_only_application_logs_expire() -> None:
    """アプリログの掃除が監査ログを巻き込まないこと（ADR-0021 の要）。"""
    remover = _SpyRemover(application_logs=5)

    outcome = PurgeExpiredLogs(remover).execute(LogRetentionPolicy(application_log_days=7), _NOW)

    assert remover.application_cutoffs == [_NOW - timedelta(days=7)]
    assert remover.audit_cutoffs == []
    assert outcome.total == 5
