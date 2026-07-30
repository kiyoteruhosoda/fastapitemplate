"""アプリログの永続化モデル（``requestId`` でリクエスト単位に追跡する）。

書き込みは :mod:`shared.kernel.logging` の ``DbLogHandler``（ログ出力は全レイヤー
横断の関心事）。閲覧のための検索は audit コンテキストが行う。

PII を含めない。ユーザー識別子は ``user_id_hash`` のみ。traceback は例外時のみ。

``level`` / ``logger`` / ``user_id_hash`` に索引を張っているのは、管理画面が
これらで絞り込むため（レベル・ロガー前方一致・利用者での検索）。
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
    level: Mapped[str] = mapped_column(sa.String(20), nullable=False, index=True)
    logger: Mapped[str] = mapped_column(sa.String(120), nullable=False, index=True)
    message = mapped_column(sa.Text(), nullable=False)
    request_id = mapped_column(sa.String(36), nullable=True, index=True)
    user_id_hash = mapped_column(sa.String(64), nullable=True, index=True)
    path = mapped_column(sa.String(255), nullable=True)
    method = mapped_column(sa.String(10), nullable=True)
    status_code = mapped_column(sa.Integer(), nullable=True)
    duration_ms = mapped_column(sa.Integer(), nullable=True)
    trace = mapped_column(sa.Text(), nullable=True)


__all__ = ["Log"]
