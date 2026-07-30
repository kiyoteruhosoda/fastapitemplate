"""システム設定 API（要 ``admin:system-settings``）。

保存は監査ログへ残す。``reason`` には**変更したキー名**だけを入れる。設定値には
SMTP パスワードのような秘密が含まれるため、値そのものは記録しない（ADR-0010）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
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

# reason 列は 255 文字。一度に多くのキーを保存しても収まるよう組み立て時に切る。
_MAX_REASON_LENGTH = 255


@router.get("", response_model=list[SystemSettingItemResponse])
async def get_config(db: DbDep) -> list[SystemSettingItemResponse]:
    return [SystemSettingItemResponse(**item) for item in SystemSettingService.effective_config(db)]


@router.put("", response_model=SystemSettingsUpdateResponse)
async def update_config(
    body: SystemSettingsUpdateRequest,
    db: DbDep,
    audit: AuditRecorderDep,
) -> SystemSettingsUpdateResponse:
    """設定を保存する。

    起動時にしか読まれない設定を変更した場合は ``restart_required`` を返す。
    実際の再起動は ``POST /api/admin/system/restart`` で要求する。
    """
    requirement = SystemSettingService.save(db, body.values)
    audit.execute(
        AuditEventType.SYSTEM_SETTINGS_UPDATED,
        target=AuditTarget.of(AuditTargetType.SYSTEM_SETTINGS),
        reason=f"keys={','.join(sorted(body.values))}"[:_MAX_REASON_LENGTH],
    )
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
