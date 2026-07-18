"""システム設定 API（要 ``admin:system-settings``）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import (
    SystemSettingItemResponse,
    SystemSettingsUpdateRequest,
)
from presentation.fastapi.schemas.auth import StatusResponse
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
    return [
        SystemSettingItemResponse(**item)
        for item in SystemSettingService.effective_config(db)
    ]


@router.put("", response_model=StatusResponse)
async def update_config(body: SystemSettingsUpdateRequest, db: DbDep) -> StatusResponse:
    SystemSettingService.save(db, body.values)
    return StatusResponse(status="ok")
