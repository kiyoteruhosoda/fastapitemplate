"""audit コンテキストの ``Depends()`` 用依存関数。

具象（SQLAlchemy 実装）の組み立てはここだけで行い、ルーターにはユースケースを
渡す。リクエスト文脈（``requestId``・接続元・操作主体）は
:mod:`shared.kernel.logging.request_context` から取り込むため、監査を記録する
ルーターは追跡情報を引数で受け取らない。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.application.use_cases.search_application_logs import (
    SearchApplicationLogs,
)
from bounded_contexts.audit.application.use_cases.search_audit_logs import (
    SearchAuditLogs,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.infrastructure.sql_application_log_repository import (
    SqlApplicationLogQuery,
)
from bounded_contexts.audit.infrastructure.sql_audit_log_repository import (
    SqlAuditEventRecorder,
    SqlAuditLogQuery,
)
from shared.kernel.database.session import get_db
from shared.kernel.logging.request_context import (
    current_actor_user_id,
    current_ip_address,
    current_request_id,
    current_user_agent,
)


def current_audit_context() -> AuditRequestContext:
    """処理中のリクエストの追跡情報を値オブジェクトへ束ねる。"""
    return AuditRequestContext(
        request_id=current_request_id(),
        ip_address=current_ip_address(),
        user_agent=current_user_agent(),
    )


def record_audit_event() -> RecordAuditEvent:
    """このリクエストの監査イベント記録口。

    書き込みは本処理と別トランザクションなので DB セッションを受け取らない
    （ロールバックされても記録が残る。ADR-0008）。
    """
    return RecordAuditEvent(
        recorder=SqlAuditEventRecorder(),
        context=current_audit_context(),
        actor_user_id=current_actor_user_id(),
    )


def search_audit_logs(db: Annotated[Session, Depends(get_db)]) -> SearchAuditLogs:
    return SearchAuditLogs(SqlAuditLogQuery(db))


def search_application_logs(db: Annotated[Session, Depends(get_db)]) -> SearchApplicationLogs:
    return SearchApplicationLogs(SqlApplicationLogQuery(db))


# 監査を記録するルーターが使う共通の型注釈
AuditRecorderDep = Annotated[RecordAuditEvent, Depends(record_audit_event)]

__all__ = [
    "AuditRecorderDep",
    "current_audit_context",
    "record_audit_event",
    "search_application_logs",
    "search_audit_logs",
]
