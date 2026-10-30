"""content_settings コンテキストの SQLAlchemy モデル（ADR-0085）。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class ContentSettingModel(Base):
    """テナントが変えたコンテンツ設定の値。既定値のままの項目は行を持たない。"""

    __tablename__ = "content_settings"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "key", name="uq_content_settings_tenant_key"),
        declared(Tenancy.TENANT),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: 値は JSON で持つ（文字列・真偽・整数）
    value: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = ["ContentSettingModel"]
