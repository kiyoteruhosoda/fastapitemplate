"""構造化ログの永続化モデル（``requestId`` でリクエスト単位に追跡する）。

PII を含めない。ユーザー識別子は ``user_id_hash`` のみ。traceback は例外時のみ。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base


class Log(Base):
    __tablename__ = "log"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, index=True)
    level: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    logger: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    message = mapped_column(sa.Text(), nullable=False)
    request_id = mapped_column(sa.String(36), nullable=True, index=True)
    user_id_hash = mapped_column(sa.String(64), nullable=True)
    path = mapped_column(sa.String(255), nullable=True)
    method = mapped_column(sa.String(10), nullable=True)
    status_code = mapped_column(sa.Integer(), nullable=True)
    duration_ms = mapped_column(sa.Integer(), nullable=True)
    trace = mapped_column(sa.Text(), nullable=True)


__all__ = ["Log"]
