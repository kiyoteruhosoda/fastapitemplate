"""Models for roles and permissions (authorization uses scope = permission code values)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infrastructure.models.base import BigIntPk
from shared.infrastructure.models.tenancy import Tenancy, declared, tenancy_info
from shared.infrastructure.models.tenant import RoleTenant
from shared.kernel.database.db import Base

role_permissions = sa.Table(
    "role_permissions",
    Base.metadata,
    sa.Column("role_id", BigIntPk, sa.ForeignKey("roles.id"), primary_key=True),
    sa.Column("permission_id", BigIntPk, sa.ForeignKey("permissions.id"), primary_key=True),
    info=tenancy_info(Tenancy.GLOBAL),
)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = declared(Tenancy.GLOBAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), unique=True, nullable=False)

    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")
    #: The tenant that created it (ADR-0079 §3). None means a template shared by all tenants.
    #: ⚠ Loaded only when accessed (when old migrations load roles through this model, the table
    #: does not exist yet).
    ownership: Mapped[RoleTenant | None] = relationship(cascade="all, delete-orphan", uselist=False)

    @property
    def tenant_id(self) -> int | None:
        return self.ownership.tenant_id if self.ownership is not None else None


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = declared(Tenancy.GLOBAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)


__all__ = ["Permission", "Role", "role_permissions"]
