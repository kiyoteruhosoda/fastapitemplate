"""アプリログを検索するユースケース（管理画面の閲覧）。"""

from __future__ import annotations

from bounded_contexts.audit.application.dto.application_log_dto import (
    ApplicationLogEntryDto,
    ApplicationLogFilterOptionsDto,
    ApplicationLogPageDto,
)
from bounded_contexts.audit.domain.entities.application_log_entry import (
    ApplicationLogEntry,
)
from bounded_contexts.audit.domain.repositories.application_log_query import (
    ApplicationLogQuery,
)
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
    LogLevel,
)


class SearchApplicationLogs:
    def __init__(self, query: ApplicationLogQuery) -> None:
        self._query = query

    def execute(self, criteria: ApplicationLogCriteria) -> ApplicationLogPageDto:
        page = self._query.search(criteria)
        return ApplicationLogPageDto(
            entries=tuple(_to_dto(entry) for entry in page.entries),
            total=page.total,
        )


class ListApplicationLogFilterOptions:
    """絞り込みに使えるログレベルの一覧を返す（画面のセレクト用）。"""

    def execute(self) -> ApplicationLogFilterOptionsDto:
        return ApplicationLogFilterOptionsDto(levels=tuple(level.value for level in LogLevel))


def _to_dto(entry: ApplicationLogEntry) -> ApplicationLogEntryDto:
    return ApplicationLogEntryDto(
        id=entry.id,
        created_at=entry.created_at.isoformat(),
        level=entry.level,
        logger=entry.logger,
        message=entry.message,
        request_id=entry.request_id,
        user_id_hash=entry.user_id_hash,
        path=entry.path,
        method=entry.method,
        status_code=entry.status_code,
        duration_ms=entry.duration_ms,
        trace=entry.trace,
    )


__all__ = ["ListApplicationLogFilterOptions", "SearchApplicationLogs"]
