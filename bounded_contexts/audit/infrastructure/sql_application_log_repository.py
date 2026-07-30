"""``log`` テーブルの検索実装（読み取り専用）。

書き込みは :mod:`shared.kernel.logging` の ``DbLogHandler`` が行う。ここは管理
画面の閲覧のために読むだけ。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.application_log_entry import (
    ApplicationLogEntry,
    ApplicationLogPage,
)
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
)
from shared.infrastructure.models.log import Log

# LIKE のメタ文字を無効化するためのエスケープ文字
_LIKE_ESCAPE = "\\"


def _escaped_for_like(value: str) -> str:
    """``%`` / ``_`` / ``\\`` を打ち消す。

    利用者の入力は「文字列」であってパターンではない。エスケープしないと
    ``%`` の 1 文字で全件一致になり、絞り込みとして機能しない。
    """
    for character in (_LIKE_ESCAPE, "%", "_"):
        value = value.replace(character, _LIKE_ESCAPE + character)
    return value


class SqlApplicationLogQuery:
    """条件に一致するアプリログを新しい順に返す。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, criteria: ApplicationLogCriteria) -> ApplicationLogPage:
        conditions = _conditions(criteria)
        total = self._session.scalar(sa.select(sa.func.count()).select_from(Log).where(*conditions)) or 0
        rows = self._session.scalars(
            sa.select(Log)
            .where(*conditions)
            .order_by(Log.created_at.desc(), Log.id.desc())
            .limit(criteria.page.limit)
            .offset(criteria.page.offset)
        ).all()
        return ApplicationLogPage(entries=tuple(_to_entry(row) for row in rows), total=total)


def _conditions(criteria: ApplicationLogCriteria) -> list[sa.ColumnElement[bool]]:
    """指定された項目だけを AND 条件として積む。"""
    conditions: list[sa.ColumnElement[bool]] = []
    if criteria.level:
        conditions.append(Log.level == criteria.level)
    if criteria.logger_prefix:
        pattern = f"{_escaped_for_like(criteria.logger_prefix)}%"
        conditions.append(Log.logger.like(pattern, escape=_LIKE_ESCAPE))
    if criteria.message_contains:
        pattern = f"%{_escaped_for_like(criteria.message_contains)}%"
        conditions.append(Log.message.like(pattern, escape=_LIKE_ESCAPE))
    if criteria.request_id:
        conditions.append(Log.request_id == criteria.request_id)
    if criteria.user_id_hash:
        conditions.append(Log.user_id_hash == criteria.user_id_hash)
    if criteria.created_from is not None:
        conditions.append(Log.created_at >= criteria.created_from)
    if criteria.created_to is not None:
        conditions.append(Log.created_at <= criteria.created_to)
    return conditions


def _to_entry(row: Log) -> ApplicationLogEntry:
    return ApplicationLogEntry(
        id=row.id,
        created_at=row.created_at,
        level=row.level,
        logger=row.logger,
        message=row.message,
        request_id=row.request_id,
        user_id_hash=row.user_id_hash,
        path=row.path,
        method=row.method,
        status_code=row.status_code,
        duration_ms=row.duration_ms,
        trace=row.trace,
    )


__all__ = ["SqlApplicationLogQuery"]
