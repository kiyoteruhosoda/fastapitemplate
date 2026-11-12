"""System settings API (``system-settings:view`` to read, ``system-settings:write`` to change;
ADR-0084 §3).

Saves are recorded in the audit log. ``reason`` holds only the **names of changed keys**.
Settings include secrets such as the SMTP password, so values are never recorded (ADR-0075 §1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
from presentation.fastapi.services.system_setting_service import SettingRefusedError, SystemSettingService
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/config",
    tags=["admin"],
)

DbDep = Annotated[Session, Depends(get_db)]

# The reason column is 255 chars. Truncate when building it so many keys saved at once still fit.
_MAX_REASON_LENGTH = 255


@router.get(
    "",
    response_model=list[SystemSettingItemResponse],
    dependencies=[Depends(require_permission("system-settings:view"))],
)
def get_config(db: DbDep) -> list[SystemSettingItemResponse]:
    return [SystemSettingItemResponse(**item) for item in SystemSettingService.effective_config(db)]


@router.put(
    "",
    response_model=SystemSettingsUpdateResponse,
    dependencies=[Depends(require_permission("system-settings:write"))],
)
def update_config(
    body: SystemSettingsUpdateRequest,
    db: DbDep,
    audit: AuditRecorderDep,
) -> SystemSettingsUpdateResponse:
    """Save settings.

    Returns ``restart_required`` if a setting read only at startup was changed.
    The actual restart is requested via ``POST /api/admin/system/restart``.
    """
    try:
        requirement = SystemSettingService.save(db, body.values)
    except SettingRefusedError as refused:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": refused.error, "key": refused.key},
        ) from refused
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
