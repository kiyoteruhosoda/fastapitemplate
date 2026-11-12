"""Model for groups (collections of users) (ADR-0081 §3).

Whereas roles decide "what one can do", groups only bundle "who and who" and hold no
permissions. The first use is notification recipients, but they are not tied to the notification
concept (they live in shared like roles, so derived apps can use them for sharing scopes etc.).

⚠ **Do not name the table ``groups``.** ``GROUPS`` is a reserved word in MySQL 8 / MariaDB and
needs quoting in raw SQL.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared, tenancy_info
from shared.kernel.database.db import Base

user_group_members = sa.Table(
    "user_group_members",
    Base.metadata,
    sa.Column("group_id", BigIntPk, sa.ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("user_id", BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    info=tenancy_info(Tenancy.PERSONAL),
)


class UserGroup(Base):
    __tablename__ = "user_groups"
    #: Names are unique within a tenant (no clash with another tenant's names; ADR-0079 §1)
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "name", name="uq_user_groups_tenant_name"),
        declared(Tenancy.TENANT),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(255), nullable=False, default="", server_default="")
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)

    members = relationship("User", secondary=user_group_members, lazy="selectin")


__all__ = ["UserGroup", "user_group_members"]
