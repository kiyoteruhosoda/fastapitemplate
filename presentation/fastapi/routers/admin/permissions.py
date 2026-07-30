"""権限コード一覧 API（要 ``permission:manage``）。

権限コードの正本は ``shared/domain/auth/master_data.py``。追加・削除は
マスタデータ + マイグレーションで行うため、この API は読み取り専用。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import PermissionResponse
from shared.infrastructure.models import Permission
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/permissions",
    tags=["admin"],
    dependencies=[Depends(require_permission("permission:manage"))],
)


@router.get("", response_model=list[PermissionResponse])
async def list_permissions(
    db: Annotated[Session, Depends(get_db)],
) -> list[PermissionResponse]:
    permissions = db.scalars(select(Permission).order_by(Permission.code)).all()
    return [PermissionResponse(id=p.id, code=p.code) for p in permissions]
