"""Search interface for audit logs (implemented in the Infrastructure layer)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.audit.domain.entities.audit_event import AuditLogPage
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    AuditLogCriteria,
)


class AuditLogQuery(Protocol):
    def search(self, criteria: AuditLogCriteria) -> AuditLogPage:
        """Return one page of rows matching *criteria*, newest first (with the total count)."""


__all__ = ["AuditLogQuery"]
