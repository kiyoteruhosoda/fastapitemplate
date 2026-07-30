"""ログ閲覧 API（要 ``log:view``）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import LogEntryResponse
from shared.infrastructure.models import Log
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/logs",
    tags=["admin"],
    dependencies=[Depends(require_permission("log:view"))],
)


@router.get("", response_model=list[LogEntryResponse])
async def list_logs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    level: str | None = None,
    request_id: str | None = None,
) -> list[LogEntryResponse]:
    query = select(Log).order_by(Log.id.desc()).limit(limit).offset(offset)
    if level:
        query = query.where(Log.level == level.upper())
    if request_id:
        query = query.where(Log.request_id == request_id)
    rows = db.scalars(query).all()
    return [
        LogEntryResponse(
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
        for row in rows
    ]
