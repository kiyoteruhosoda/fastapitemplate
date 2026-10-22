"""``audit_log`` テーブルの SQLAlchemy 実装（書き込みと検索）。

書き込みは**リクエストのセッションとは別のトランザクション**（専用の短命コネクション）
で行う。ログイン失敗は ``HTTPException`` で終わり、リクエストのセッションは
ロールバックされるため、同じセッションで書くと「失敗したログイン」が記録されない
（ADR-0013）。

呼ばれるのは**リクエストの処理が完全に終わってから**（audit ミドルウェア）。処理の
途中で呼ぶと、SQLite ではリクエストのセッションが持つ書き込みロックと衝突して
``database is locked`` になる。

検索はリクエストのセッションで読む（読み取りは本処理の状態を汚さない）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEvent,
    AuditLogEntry,
    AuditLogPage,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    MAX_IP_ADDRESS_LENGTH,
    MAX_REQUEST_ID_LENGTH,
    MAX_USER_AGENT_LENGTH,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    MAX_TARGET_ID_LENGTH,
    MAX_TARGET_TYPE_LENGTH,
    AuditTargetType,
)
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    AuditLogCriteria,
)
from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from shared.infrastructure.models import UserTenant
from shared.kernel.database.db import get_engine

MAX_REASON_LENGTH = 255


def _clipped(value: str | None, limit: int) -> str | None:
    """列の長さ上限に収める（超過分は末尾を落とす）。"""
    if value is None:
        return None
    return value[:limit]


class SqlAuditEventRecorder:
    """監査イベントを独立したトランザクションでまとめて書き込む。"""

    def record_all(self, events: Sequence[AuditEvent]) -> None:
        if not events:
            return
        with get_engine().begin() as connection:
            tenants = _tenants_of(connection, {uid for event in events for uid in _people_of(event)})
            rows = [_to_row(event, _tenant_of(event, tenants)) for event in events]
            connection.execute(sa.insert(AuditLogModel), rows)


def _people_of(event: AuditEvent) -> tuple[int, ...]:
    """テナントを決める材料になる利用者（実行者・対象の利用者）。"""
    people: list[int] = []
    if event.actor_user_id is not None:
        people.append(event.actor_user_id)
    target = event.target
    if target is not None and target.type is AuditTargetType.USER and (target.identifier or "").isdigit():
        people.append(int(target.identifier or "0"))
    return tuple(people)


def _tenants_of(connection: sa.Connection, user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = connection.execute(
        sa.select(UserTenant.user_id, UserTenant.tenant_id).where(UserTenant.user_id.in_(user_ids))
    ).all()
    return {int(user_id): int(tenant_id) for user_id, tenant_id in rows}


def _tenant_of(event: AuditEvent, tenants: dict[int, int]) -> int | None:
    """どのテナントの記録か（ADR-0061）。

    実行者のテナント。実行者がテナントに属さない（システム管理者・未認証の失敗）ときは、
    対象の利用者のテナント ——システム管理者がテナントの人に触れた事実は、そのテナントの
    管理者に見えるようにする。どちらも無ければ全体の記録（``None``）。
    """
    for user_id in _people_of(event):
        if user_id in tenants:
            return tenants[user_id]
    return None


def _to_row(event: AuditEvent, tenant_id: int | None) -> dict[str, object]:
    """DDL の長さ上限に収めた 1 行分の値。"""
    target = event.target
    return {
        "tenant_id": tenant_id,
        "occurred_at": event.occurred_at,
        "event_type": str(event.event_type),
        "result": str(event.result),
        "actor_user_id": event.actor_user_id,
        "target_type": _clipped(str(target.type) if target else None, MAX_TARGET_TYPE_LENGTH),
        "target_id": _clipped(target.identifier if target else None, MAX_TARGET_ID_LENGTH),
        "ip_address": _clipped(event.context.ip_address, MAX_IP_ADDRESS_LENGTH),
        "user_agent": _clipped(event.context.user_agent, MAX_USER_AGENT_LENGTH),
        "reason": _clipped(event.reason, MAX_REASON_LENGTH),
        "request_id": _clipped(event.context.request_id, MAX_REQUEST_ID_LENGTH),
    }


class SqlAuditLogQuery:
    """条件に一致する監査ログを新しい順に返す。

    見えるのは**読む人のテナントの記録だけ**（ADR-0061）。テナントに属さない人
    （システム管理者）には、全体の記録（``tenant_id`` が NULL）だけが見える。
    """

    def __init__(self, session: Session, tenant_id: int | None) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def search(self, criteria: AuditLogCriteria) -> AuditLogPage:
        conditions = [_within_tenant(self._tenant_id), *_conditions(criteria)]
        total = self._session.scalar(sa.select(sa.func.count()).select_from(AuditLogModel).where(*conditions)) or 0
        rows = self._session.scalars(
            sa.select(AuditLogModel)
            .where(*conditions)
            .order_by(AuditLogModel.occurred_at.desc(), AuditLogModel.id.desc())
            .limit(criteria.page.limit)
            .offset(criteria.page.offset)
        ).all()
        return AuditLogPage(entries=tuple(_to_entry(row) for row in rows), total=total)


def _within_tenant(tenant_id: int | None) -> sa.ColumnElement[bool]:
    if tenant_id is None:
        return AuditLogModel.tenant_id.is_(None)
    return AuditLogModel.tenant_id == tenant_id


def _conditions(criteria: AuditLogCriteria) -> list[sa.ColumnElement[bool]]:
    """指定された項目だけを AND 条件として積む。"""
    conditions: list[sa.ColumnElement[bool]] = []
    if criteria.event_type:
        conditions.append(AuditLogModel.event_type == criteria.event_type)
    if criteria.result:
        conditions.append(AuditLogModel.result == criteria.result)
    if criteria.actor_user_id is not None:
        conditions.append(AuditLogModel.actor_user_id == criteria.actor_user_id)
    if criteria.target_type:
        conditions.append(AuditLogModel.target_type == criteria.target_type)
    if criteria.target_id:
        conditions.append(AuditLogModel.target_id == criteria.target_id)
    if criteria.request_id:
        conditions.append(AuditLogModel.request_id == criteria.request_id)
    if criteria.occurred_from is not None:
        conditions.append(AuditLogModel.occurred_at >= criteria.occurred_from)
    if criteria.occurred_to is not None:
        conditions.append(AuditLogModel.occurred_at <= criteria.occurred_to)
    return conditions


def _to_entry(row: AuditLogModel) -> AuditLogEntry:
    return AuditLogEntry(
        id=row.id,
        occurred_at=row.occurred_at,
        event_type=row.event_type,
        result=row.result,
        actor_user_id=row.actor_user_id,
        target_type=row.target_type,
        target_id=row.target_id,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        reason=row.reason,
        request_id=row.request_id,
    )


__all__ = ["MAX_REASON_LENGTH", "SqlAuditEventRecorder", "SqlAuditLogQuery"]
