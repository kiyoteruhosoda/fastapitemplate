"""グループ（利用者のまとまり）のモデル（ADR-0047）。

ロールが「何ができるか」を決めるのに対し、グループは「誰と誰か」を束ねるだけで
権限を持たない。通知の宛先に使うのが最初の用途だが、通知の概念には閉じていない
（派生アプリが共有範囲などにも使えるよう、ロールと同じく shared に置く）。

⚠ **テーブル名は ``groups`` にしない。** MySQL 8 / MariaDB では ``GROUPS`` が予約語で、
素の SQL で書くと引用符が要る。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base

user_group_members = sa.Table(
    "user_group_members",
    Base.metadata,
    sa.Column("group_id", BigIntPk, sa.ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("user_id", BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(sa.String(255), nullable=False, default="", server_default="")
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)

    members = relationship("User", secondary=user_group_members, lazy="selectin")


__all__ = ["UserGroup", "user_group_members"]
