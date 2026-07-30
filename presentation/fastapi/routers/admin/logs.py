"""ログ閲覧 API（要 ``log:view``）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import LogEntryResponse, LogSearchRequest
from shared.infrastructure.models import Log
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/logs",
    tags=["admin"],
    dependencies=[Depends(require_permission("log:view"))],
)


def _query_for(search: LogSearchRequest) -> Select[tuple[Log]]:
    query = select(Log).order_by(Log.id.desc()).limit(search.limit).offset(search.offset)
    if search.level:
        query = query.where(Log.level == search.level.upper())
    if search.request_id:
        query = query.where(Log.request_id == search.request_id)
    return query


def _to_response(row: Log) -> LogEntryResponse:
    return LogEntryResponse(
        id=row.id,
        created_at=row.created_at.isoformat(),
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


@router.get("", response_model=list[LogEntryResponse])
async def list_logs(
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[LogSearchRequest, Query()],
) -> list[LogEntryResponse]:
    return [_to_response(row) for row in db.scalars(_query_for(search)).all()]
