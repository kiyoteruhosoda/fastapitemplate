"""Use case that deletes logs past their retention period.

Called from periodic execution (a resident thread). If the setting is "never delete" (the
default), the DB is not touched at all (ADR-0075 §3).

The number of deleted rows is written to the application log, so operators can check on the admin
screen "is the cleanup working" and "how much is deleted at a time". Rounds that delete nothing
write nothing (avoids piling up the same line on every run).
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
    """Number of rows deleted by one cleanup."""

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
                "Deleted logs past their retention period",
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
