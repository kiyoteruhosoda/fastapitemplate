"""システム設定 API（要 ``admin:system-settings``）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import (
    RestartRequirementResponse,
    SystemSettingItemResponse,
    SystemSettingsUpdateRequest,
    SystemSettingsUpdateResponse,
)
from presentation.fastapi.services.system_setting_service import SystemSettingService
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/config",
    tags=["admin"],
    dependencies=[Depends(require_permission("admin:system-settings"))],
)

DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[SystemSettingItemResponse])
async def get_config(db: DbDep) -> list[SystemSettingItemResponse]:
    return [SystemSettingItemResponse(**item) for item in SystemSettingService.effective_config(db)]


@router.put("", response_model=SystemSettingsUpdateResponse)
async def update_config(body: SystemSettingsUpdateRequest, db: DbDep) -> SystemSettingsUpdateResponse:
    """設定を保存する。

    起動時にしか読まれない設定を変更した場合は ``restart_required`` を返す。
    実際の再起動は ``POST /api/admin/system/restart`` で要求する。
    """
    requirement = SystemSettingService.save(db, body.values)
    return SystemSettingsUpdateResponse(
        status="ok",
        restart_required=(
            RestartRequirementResponse(
                scopes=[scope.value for scope in requirement.scopes],
                keys=list(requirement.keys),
            )
            if requirement
            else None
        ),
    )
