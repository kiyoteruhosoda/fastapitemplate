"""システム設定の永続化モデル（``settings`` の DB 上書き層が参照する）。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import utcnow
from shared.kernel.database.db import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    setting_json = mapped_column(sa.JSON(), nullable=False)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = ["SystemSetting"]
