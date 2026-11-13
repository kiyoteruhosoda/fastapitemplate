"""Cleanup of logs past their retention period (assembling the periodic execution).

Wiring that connects the use case (Application) with the deletion implementation (Infrastructure).
Infrastructure cannot import Application, so the outermost layer does the assembly.

**Settings are read on every run.** Changing the retention days on the admin screen takes effect
from the next round (no restart needed = the setting definition has no ``restart_scopes``).
"""

from __future__ import annotations

from bounded_contexts.audit.application.use_cases.purge_expired_logs import (
    PurgeExpiredLogs,
)
from bounded_contexts.audit.domain.value_objects.retention_policy import (
    LogRetentionPolicy,
)
from bounded_contexts.audit.infrastructure.sql_expired_log_remover import (
    SqlExpiredLogRemover,
)
from shared.kernel.scheduling import start_interval_worker
from shared.kernel.timestamps import utcnow

WORKER_NAME = "log-retention"

# Cleanup interval. Retention is in days, so checking a few times a day is enough (not a setting:
# operators decide "how many days to keep", not "how many seconds between checks").
PURGE_INTERVAL_SECONDS = 6 * 60 * 60


def purge_expired_logs_once() -> None:
    """Run one cleanup according to the current settings."""
    from shared.kernel.settings.settings import settings

    policy = LogRetentionPolicy(
        application_log_days=settings.log_retention_days,
        audit_log_days=settings.audit_log_retention_days,
    )
    PurgeExpiredLogs(SqlExpiredLogRemover()).execute(policy, utcnow())


def start_log_retention_worker() -> None:
    """Start periodic cleanup (call from the process's startup)."""
    start_interval_worker(WORKER_NAME, purge_expired_logs_once, PURGE_INTERVAL_SECONDS)


__all__ = ["PURGE_INTERVAL_SECONDS", "WORKER_NAME", "purge_expired_logs_once", "start_log_retention_worker"]
