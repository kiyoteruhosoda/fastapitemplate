"""監査ログの検索インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.audit.domain.entities.audit_event import AuditLogPage
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    AuditLogCriteria,
)


class AuditLogQuery(Protocol):
    def search(self, criteria: AuditLogCriteria) -> AuditLogPage:
        """*criteria* に一致する行を新しい順に 1 ページ返す（総件数付き）。"""


__all__ = ["AuditLogQuery"]
