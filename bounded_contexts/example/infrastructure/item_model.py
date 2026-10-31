"""example コンテキスト固有の SQLAlchemy モデル。

コンテキスト固有のテーブルは shared ではなく各コンテキストの
infrastructure に置く。Alembic が認識できるよう ``migrations/env.py`` へ
import を追加すること。
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class ItemModel(Base):
    __tablename__ = "items"
    __table_args__ = declared(Tenancy.TENANT)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = ["ItemModel"]
