"""Models for tenants and user membership (ADR-0079 §1).

One tenant row corresponds to one assay tenant. Identified by its issuer (``issuer``); the client
ID is also held per tenant (assay clients are registered per tenant).

User membership is held in a separate one-to-one table ``user_tenants``, not as a ``users`` column.
⚠ An old migration (the setup ``0002``) writes ``users`` through the ``User`` model, so adding a
column breaks at a step before the migration that adds it (same reason as
``user_session_boundaries``).
Only system administrators have no membership (ADR-0079 §1 decision 3).
"""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class TenantStatus(StrEnum):
    ACTIVE = "active"
    #: A suspended tenant. Users cannot sign in, and refreshes do not reissue tokens.
    SUSPENDED = "suspended"


# No DB-native ENUM (becomes a VARCHAR with a CHECK constraint)
_TENANT_STATUS = sa.Enum(*(s.value for s in TenantStatus), name="tenant_status", native_enum=False)


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = declared(Tenancy.GLOBAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    #: Short name used in URLs (``/t/<slug>/login``).
    slug: Mapped[str] = mapped_column(sa.String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: Issuer of the assay tenant. NULL means "a tenant that does not use SSO (local accounts only)".
    issuer: Mapped[str | None] = mapped_column(sa.String(255), unique=True, nullable=True)
    #: This app's client ID registered in that tenant.
    client_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        _TENANT_STATUS, nullable=False, default=TenantStatus.ACTIVE.value, server_default=TenantStatus.ACTIVE.value
    )
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE.value


class UserTenant(Base):
    """A user's membership (one row per user)."""

    __tablename__ = "user_tenants"
    __table_args__ = declared(Tenancy.PERSONAL)

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)


class RoleTenant(Base):
    """Owner of a role a tenant created itself (one row per role; ADR-0079 §3).

    Roles without a row are templates (``master_data.ROLES``) shared by all tenants. A tenant's
    admins cannot change the content of shared roles (it would change other tenants' permissions).
    """

    __tablename__ = "role_tenants"
    __table_args__ = declared(Tenancy.TENANT)

    role_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)


__all__ = ["RoleTenant", "Tenant", "TenantStatus", "UserTenant"]
