"""Interface for deleting rows past their retention period (implemented in the Infrastructure layer).

Kept separate from the search interfaces (``ApplicationLogQuery`` / ``AuditLogQuery``). Reads use
the request's session, whereas deletion runs in independent transactions in small batches, with a
different lifetime and caller (ADR-0075 §3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ExpiredLogRemover(Protocol):
    def delete_application_logs_before(self, cutoff: datetime) -> int:
        """Delete application logs older than *cutoff* and return the number of rows deleted."""

    def delete_audit_logs_before(self, cutoff: datetime) -> int:
        """Delete audit logs older than *cutoff* and return the number of rows deleted."""


__all__ = ["ExpiredLogRemover"]
