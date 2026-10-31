"""権限コード一覧 API（要 ``role:manage``。ロールを定義するために読む。ADR-0084 §3）。

権限コードの正本は ``shared/domain/auth/master_data.py``。追加・削除は
マスタデータ + マイグレーションで行うため、この API は読み取り専用。

テナントのロールに付けられない全体の権限（``SYSTEM_PERMISSIONS``）は出さない（ADR-0079 §1）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import PermissionResponse
from shared.domain.auth.master_data import SYSTEM_PERMISSIONS
from shared.infrastructure.models import Permission
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/permissions",
    tags=["admin"],
    dependencies=[Depends(require_permission("role:manage"))],
)


@router.get("", response_model=list[PermissionResponse])
def list_permissions(
    db: Annotated[Session, Depends(get_db)],
) -> list[PermissionResponse]:
    permissions = db.scalars(
        select(Permission).where(Permission.code.not_in(list(SYSTEM_PERMISSIONS))).order_by(Permission.code)
    ).all()
    return [PermissionResponse(id=p.id, code=p.code) for p in permissions]
