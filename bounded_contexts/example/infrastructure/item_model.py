"""example コンテキスト固有の SQLAlchemy モデル。

コンテキスト固有のテーブルは shared ではなく各コンテキストの
infrastructure に置く。Alembic が認識できるよう ``migrations/env.py`` へ
import を追加すること。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk
from shared.kernel.database.db import Base


class ItemModel(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)


__all__ = ["ItemModel"]
