"""Log retention periods.

``log`` and ``audit_log`` differ in nature, so they have separate day counts (ADR-0075 §3).
Application logs are numerous and short-lived and may be trimmed, while audit logs record "who
did what" and have no rows that may be deleted.

``0`` means "never delete". Retention is decided by operational and audit requirements, and the
template should not start deleting by default, so both default to ``0``. Negative day counts are
treated the same (a typo in the setting must not delete even the most recent rows).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

KEEP_FOREVER = 0


@dataclass(frozen=True, slots=True)
class LogRetentionPolicy:
    """Which table to keep for how many days."""

    application_log_days: int = KEEP_FOREVER
    audit_log_days: int = KEEP_FOREVER

    @property
    def purges_nothing(self) -> bool:
        """Whether neither table is subject to deletion."""
        return self.application_log_days <= KEEP_FOREVER and self.audit_log_days <= KEEP_FOREVER

    def application_log_cutoff(self, now: datetime) -> datetime | None:
        """Boundary before which application logs are deleted. ``None`` if set to never delete."""
        return _cutoff(self.application_log_days, now)

    def audit_log_cutoff(self, now: datetime) -> datetime | None:
        """Boundary before which audit logs are deleted. ``None`` if set to never delete."""
        return _cutoff(self.audit_log_days, now)


def _cutoff(days: int, now: datetime) -> datetime | None:
    if days <= KEEP_FOREVER:
        return None
    return now - timedelta(days=days)


__all__ = ["KEEP_FOREVER", "LogRetentionPolicy"]
