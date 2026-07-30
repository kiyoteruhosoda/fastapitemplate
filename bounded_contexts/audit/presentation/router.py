"""ログ閲覧 API（監査ログ・アプリログ）。

2 つのルーターに分けているのは必要な scope が違うため。

============= ============================= ===============
記録           エンドポイント                 必要 scope
============= ============================= ===============
監査ログ       ``/api/admin/audit-logs``     ``audit:view``
アプリログ     ``/api/admin/logs``           ``log:view``
============= ============================= ===============

``request_id`` はどちらの記録にも入るので、片方で見つけた ID をもう一方の
絞り込みに入れれば「そのリクエストで何が起きたか」を突き合わせられる。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from bounded_contexts.audit.application.dto.application_log_dto import (
    ApplicationLogEntryDto,
)
from bounded_contexts.audit.application.dto.audit_log_dto import AuditLogEntryDto
from bounded_contexts.audit.application.use_cases.search_application_logs import (
    ListApplicationLogFilterOptions,
    SearchApplicationLogs,
)
from bounded_contexts.audit.application.use_cases.search_audit_logs import (
    ListAuditLogFilterOptions,
    SearchAuditLogs,
)
from bounded_contexts.audit.domain.value_objects.log_page import LogPage
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
    AuditLogCriteria,
)
from bounded_contexts.audit.presentation import dependencies
from bounded_contexts.audit.presentation.schemas import (
    AuditLogEntryResponse,
    AuditLogFilterOptionsResponse,
    AuditLogSearchRequest,
    AuditLogSearchResponse,
    LogEntryResponse,
    LogFilterOptionsResponse,
    LogSearchRequest,
    LogSearchResponse,
)
from presentation.fastapi.dependencies.auth import require_permission
from shared.kernel.timestamps import to_naive_utc

audit_log_router = APIRouter(
    prefix="/api/admin/audit-logs",
    tags=["admin"],
    dependencies=[Depends(require_permission("audit:view"))],
)

application_log_router = APIRouter(
    prefix="/api/admin/logs",
    tags=["admin"],
    dependencies=[Depends(require_permission("log:view"))],
)

SearchAuditLogsDep = Annotated[SearchAuditLogs, Depends(dependencies.search_audit_logs)]
SearchApplicationLogsDep = Annotated[SearchApplicationLogs, Depends(dependencies.search_application_logs)]


# ---------------------------------------------------------------------------
# 監査ログ（誰が何をしたか）
# ---------------------------------------------------------------------------


@audit_log_router.get("", response_model=AuditLogSearchResponse)
async def search_audit_logs(
    query: Annotated[AuditLogSearchRequest, Query()],
    use_case: SearchAuditLogsDep,
) -> AuditLogSearchResponse:
    """監査ログを条件で絞り込み、新しい順に 1 ページ返す。"""
    criteria = AuditLogCriteria(
        event_type=query.event_type,
        result=query.result,
        actor_user_id=query.actor_user_id,
        target_type=query.target_type,
        target_id=query.target_id,
        request_id=query.request_id,
        occurred_from=to_naive_utc(query.occurred_from),
        occurred_to=to_naive_utc(query.occurred_to),
        page=LogPage.of(query.limit, query.offset),
    )
    page = use_case.execute(criteria)
    return AuditLogSearchResponse(
        total=page.total,
        entries=[_to_audit_response(entry) for entry in page.entries],
    )


@audit_log_router.get("/filters", response_model=AuditLogFilterOptionsResponse)
async def audit_log_filter_options() -> AuditLogFilterOptionsResponse:
    """絞り込みに使える監査イベント種別・結果・対象種別の一覧。"""
    options = ListAuditLogFilterOptions().execute()
    return AuditLogFilterOptionsResponse(
        event_types=list(options.event_types),
        results=list(options.results),
        target_types=list(options.target_types),
    )


# ---------------------------------------------------------------------------
# アプリログ（システムが何をしたか）
# ---------------------------------------------------------------------------


@application_log_router.get("", response_model=LogSearchResponse)
async def search_application_logs(
    query: Annotated[LogSearchRequest, Query()],
    use_case: SearchApplicationLogsDep,
) -> LogSearchResponse:
    """アプリログを条件で絞り込み、新しい順に 1 ページ返す。"""
    criteria = ApplicationLogCriteria(
        level=query.level,
        logger_prefix=query.logger,
        message_contains=query.message,
        request_id=query.request_id,
        user_id_hash=query.user_id_hash,
        created_from=to_naive_utc(query.created_from),
        created_to=to_naive_utc(query.created_to),
        page=LogPage.of(query.limit, query.offset),
    )
    page = use_case.execute(criteria)
    return LogSearchResponse(
        total=page.total,
        entries=[_to_log_response(entry) for entry in page.entries],
    )


@application_log_router.get("/filters", response_model=LogFilterOptionsResponse)
async def application_log_filter_options() -> LogFilterOptionsResponse:
    """絞り込みに使えるログレベルの一覧。"""
    return LogFilterOptionsResponse(levels=list(ListApplicationLogFilterOptions().execute().levels))


def _to_audit_response(entry: AuditLogEntryDto) -> AuditLogEntryResponse:
    return AuditLogEntryResponse(
        id=entry.id,
        occurred_at=entry.occurred_at,
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


def _to_log_response(entry: ApplicationLogEntryDto) -> LogEntryResponse:
    return LogEntryResponse(
        id=entry.id,
        created_at=entry.created_at,
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


__all__ = ["application_log_router", "audit_log_router"]
