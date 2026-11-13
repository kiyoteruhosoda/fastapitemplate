"""Content settings API (ADR-0084 §3, ADR-0085).

Viewing needs ``content-settings:view``; changing needs ``content-settings:write``.

Only affects the principal's own tenant. Changes record the item names in the audit log (not the values).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.content_settings.application.use_cases.content_settings_book import ContentSettingsBook
from bounded_contexts.content_settings.domain.exceptions import ContentSettingError
from bounded_contexts.content_settings.infrastructure.sql_content_setting_repository import (
    SqlContentSettingRepository,
)
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.dependencies.tenant import TenantIdDep
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/admin/content-settings", tags=["admin"])

#: The reason column is 255 characters
_MAX_REASON_LENGTH = 255


class ContentSettingResponse(BaseModel):
    key: str
    value_type: str
    value: str | bool | int
    default: str | bool | int
    #: Whether the tenant saved a value (false means the default is in effect)
    stored: bool
    choices: list[str]
    minimum: int | None
    maximum: int | None


class ContentSettingsUpdateRequest(BaseModel):
    #: Key -> new value. ``null`` resets to the default
    values: dict[str, str | bool | int | None]


def get_content_settings_book(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: TenantIdDep,
) -> ContentSettingsBook:
    return ContentSettingsBook(SqlContentSettingRepository(db, tenant_id))


BookDep = Annotated[ContentSettingsBook, Depends(get_content_settings_book)]


def _listed(book: ContentSettingsBook) -> list[ContentSettingResponse]:
    return [
        ContentSettingResponse(
            key=e.key,
            value_type=e.value_type,
            value=e.value,
            default=e.default,
            stored=e.stored,
            choices=list(e.choices),
            minimum=e.minimum,
            maximum=e.maximum,
        )
        for e in book.entries()
    ]


@router.get(
    "",
    response_model=list[ContentSettingResponse],
    dependencies=[Depends(require_permission("content-settings:view"))],
)
def list_content_settings(book: BookDep) -> list[ContentSettingResponse]:
    return _listed(book)


@router.put(
    "",
    response_model=list[ContentSettingResponse],
    dependencies=[Depends(require_permission("content-settings:write"))],
)
def update_content_settings(
    body: ContentSettingsUpdateRequest, book: BookDep, audit: AuditRecorderDep
) -> list[ContentSettingResponse]:
    try:
        changed = book.change(body.values)
    except ContentSettingError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"error": error.code, "key": error.key}
        ) from error
    if changed:
        audit.execute(
            AuditEventType.CONTENT_SETTINGS_UPDATED,
            target=AuditTarget.of(AuditTargetType.CONTENT_SETTINGS),
            reason=f"keys={','.join(changed)}"[:_MAX_REASON_LENGTH],
        )
    return _listed(book)


__all__ = ["get_content_settings_book", "router"]
