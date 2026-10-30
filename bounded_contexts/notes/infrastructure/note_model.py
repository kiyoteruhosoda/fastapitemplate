"""notes コンテキストの SQLAlchemy モデル（ADR-0070 の見本）。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class NoteModel(Base):
    __tablename__ = "notes"
    __table_args__ = declared(Tenancy.TENANT)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    #: 持ち主。消えたらメモも消える
    owner_user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: 共有先のグループ。グループを消すと共有が外れ、持ち主だけのメモに戻る
    shared_group_id: Mapped[int | None] = mapped_column(
        BigIntPk, sa.ForeignKey("user_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    body: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = ["NoteModel"]
