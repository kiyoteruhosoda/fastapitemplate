"""保持期間を過ぎたログを削除するユースケース。

定期実行（常駐スレッド）から呼ばれる。設定が「削除しない」（既定）なら DB を
一切触らない（ADR-0021）。

削除した行数はアプリログへ残す。運用者が「掃除が効いているか」「一度にどれだけ
消えているか」を管理画面から確かめられるようにするため。何も消さなかった回は
書かない（定期実行のたびに同じ行が積み上がるのを避ける）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.audit.domain.repositories.expired_log_remover import (
    ExpiredLogRemover,
)
from bounded_contexts.audit.domain.value_objects.retention_policy import (
    LogRetentionPolicy,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PurgeOutcome:
    """1 回の掃除で消えた行数。"""

    application_logs: int = 0
    audit_logs: int = 0

    @property
    def total(self) -> int:
        return self.application_logs + self.audit_logs


class PurgeExpiredLogs:
    def __init__(self, remover: ExpiredLogRemover) -> None:
        self._remover = remover

    def execute(self, policy: LogRetentionPolicy, now: datetime) -> PurgeOutcome:
        if policy.purges_nothing:
            return PurgeOutcome()

        outcome = PurgeOutcome(
            application_logs=self._purge_application_logs(policy, now),
            audit_logs=self._purge_audit_logs(policy, now),
        )
        if outcome.total:
            logger.info(
                "保持期間を過ぎたログを削除しました",
                extra={
                    "event": "log.retention.purged",
                    "deleted_application_logs": outcome.application_logs,
                    "deleted_audit_logs": outcome.audit_logs,
                },
            )
        return outcome

    def _purge_application_logs(self, policy: LogRetentionPolicy, now: datetime) -> int:
        cutoff = policy.application_log_cutoff(now)
        if cutoff is None:
            return 0
        return self._remover.delete_application_logs_before(cutoff)

    def _purge_audit_logs(self, policy: LogRetentionPolicy, now: datetime) -> int:
        cutoff = policy.audit_log_cutoff(now)
        if cutoff is None:
            return 0
        return self._remover.delete_audit_logs_before(cutoff)


__all__ = ["PurgeExpiredLogs", "PurgeOutcome"]
