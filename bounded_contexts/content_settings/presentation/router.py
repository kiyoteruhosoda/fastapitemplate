"""コンテンツ設定の API（ADR-0084 §3・ADR-0085）。

見るには ``content-settings:view``、変えるには ``content-settings:write``。

効くのは主体のテナントの中だけ。変えたら監査ログに項目名を残す（値は残さない）。
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

#: reason 列は 255 文字
_MAX_REASON_LENGTH = 255


class ContentSettingResponse(BaseModel):
    key: str
    value_type: str
    value: str | bool | int
    default: str | bool | int
    #: テナントが値を保存しているか（偽なら既定値で動いている）
    stored: bool
    choices: list[str]
    minimum: int | None
    maximum: int | None


class ContentSettingsUpdateRequest(BaseModel):
    #: キー → 新しい値。``null`` は既定値へ戻す
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
async def list_content_settings(book: BookDep) -> list[ContentSettingResponse]:
    return _listed(book)


@router.put(
    "",
    response_model=list[ContentSettingResponse],
    dependencies=[Depends(require_permission("content-settings:write"))],
)
async def update_content_settings(
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
