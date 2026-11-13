"""Schemas for the system administrator API (outside tenants; ADR-0079 §1, §5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from presentation.fastapi.schemas.types import UtcDatetime

#: Short tenant name used in URLs (``/t/<slug>/login``)
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,49}$"


class TenantResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    issuer: str | None
    client_id: str | None
    status: str
    #: Count only (members are not shown)
    member_count: int
    active_member_count: int
    created_at: UtcDatetime


class DesignationRequest(BaseModel):
    """Person to appoint as tenant administrator (ADR-0079 §5). They receive an invitation email."""

    email: EmailStr
    username: str = Field(min_length=1, max_length=100)


#: Roles for people outside tenants (``master_data.SYSTEM_ROLES``; ADR-0084 §4)
SystemRoleName = Literal["system-admin", "system-support"]


class SystemPersonRequest(DesignationRequest):
    """Add a person outside tenants (operator or support staff). They receive an invitation email."""

    role: SystemRoleName = "system-admin"


class TenantCreateRequest(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    display_name: str = Field(min_length=1, max_length=100)
    #: Issuer of the assay tenant. Empty means a tenant without SSO (local accounts only)
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
    #: Whether the invitation email was sent (false if mail is disabled; the seat can then be
    #: claimed by signing in via the IdP)
    invitation_sent: bool


class TenantCreatedResponse(BaseModel):
    tenant: TenantResponse
    designation: DesignationResponse


class SystemAdministratorResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    #: ``system-admin`` (operator) or ``system-support`` (support staff)
    role: str | None


__all__ = [
    "SLUG_PATTERN",
    "DesignationRequest",
    "DesignationResponse",
    "SystemAdministratorResponse",
    "SystemPersonRequest",
    "SystemRoleName",
    "TenantCreateRequest",
    "TenantCreatedResponse",
    "TenantResponse",
    "TenantUpdateRequest",
]
