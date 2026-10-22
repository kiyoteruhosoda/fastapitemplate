"""ロール・権限のモデル（認可は scope = 権限コード値で行う）。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infrastructure.models.base import BigIntPk
from shared.infrastructure.models.tenancy import Tenancy, declared, tenancy_info
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


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = declared(Tenancy.GLOBAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)


__all__ = ["Permission", "Role", "role_permissions"]
