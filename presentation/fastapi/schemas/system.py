"""システム管理者の API（テナントの外側。ADR-0061・ADR-0065）のスキーマ。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from presentation.fastapi.schemas.types import UtcDatetime

#: URL に使うテナントの短い名前（``/t/<slug>/login``）
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,49}$"


class TenantResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    issuer: str | None
    client_id: str | None
    status: str
    #: 人数だけ（中身は見せない）
    member_count: int
    active_member_count: int
    created_at: UtcDatetime


class DesignationRequest(BaseModel):
    """テナント管理者に指名する人（ADR-0065）。本人には招待のメールが届く。"""

    email: EmailStr
    username: str = Field(min_length=1, max_length=100)


class TenantCreateRequest(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    display_name: str = Field(min_length=1, max_length=100)
    #: assay のテナントの発行者。空なら SSO を使わない（ローカル口座だけの）テナント
    issuer: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    first_admin: DesignationRequest


class TenantUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    issuer: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    status: Literal["active", "suspended"] | None = None


class DesignationResponse(BaseModel):
    user_id: int
    #: 招待のメールを送れたか（メールが止めてあれば偽。そのときは IdP で入れば席を受け取れる）
    invitation_sent: bool


class TenantCreatedResponse(BaseModel):
    tenant: TenantResponse
    designation: DesignationResponse


class SystemAdministratorResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool


__all__ = [
    "SLUG_PATTERN",
    "DesignationRequest",
    "DesignationResponse",
    "SystemAdministratorResponse",
    "TenantCreateRequest",
    "TenantCreatedResponse",
    "TenantResponse",
    "TenantUpdateRequest",
]
