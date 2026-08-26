"""監査ログを検索するユースケース（管理画面の閲覧）。"""

from __future__ import annotations

from bounded_contexts.audit.application.dto.audit_log_dto import (
    AuditLogEntryDto,
    AuditLogFilterOptionsDto,
    AuditLogPageDto,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditLogEntry,
    AuditResult,
)
from bounded_contexts.audit.domain.repositories.audit_log_query import AuditLogQuery
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTargetType
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    AuditLogCriteria,
)
from shared.kernel.timestamps import isoformat_utc


class SearchAuditLogs:
    def __init__(self, query: AuditLogQuery) -> None:
        self._query = query

    def execute(self, criteria: AuditLogCriteria) -> AuditLogPageDto:
        page = self._query.search(criteria)
        return AuditLogPageDto(
            entries=tuple(_to_dto(entry) for entry in page.entries),
            total=page.total,
        )


class ListAuditLogFilterOptions:
    """絞り込みに使える値の一覧を返す。

    画面に列挙を写して二重管理しないための入口。DB を読まない（現在定義されて
    いる監査イベント種別そのものが答え）。
    """

    def execute(self) -> AuditLogFilterOptionsDto:
        return AuditLogFilterOptionsDto(
            event_types=tuple(sorted(event_type.value for event_type in AuditEventType)),
            results=tuple(result.value for result in AuditResult),
            target_types=tuple(sorted(target_type.value for target_type in AuditTargetType)),
        )


def _to_dto(entry: AuditLogEntry) -> AuditLogEntryDto:
    return AuditLogEntryDto(
        id=entry.id,
        occurred_at=isoformat_utc(entry.occurred_at),
        event_type=entry.event_type,
        result=entry.result,
        actor_user_id=entry.actor_user_id,
        target_type=entry.target_type,
        target_id=entry.target_id,
        ip_address=entry.ip_address,
        user_agent=entry.user_agent,
        reason=entry.reason,
        request_id=entry.request_id,
    )


__all__ = ["ListAuditLogFilterOptions", "SearchAuditLogs"]
