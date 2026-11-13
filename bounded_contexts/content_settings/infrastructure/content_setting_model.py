"""SQLAlchemy models of the content_settings context (ADR-0085)."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class ContentSettingModel(Base):
    """Content setting values a tenant changed. Items left at the default have no row."""

    __tablename__ = "content_settings"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "key", name="uq_content_settings_tenant_key"),
        declared(Tenancy.TENANT),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: The value is stored as JSON (string, bool or integer)
    value: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = ["ContentSettingModel"]
