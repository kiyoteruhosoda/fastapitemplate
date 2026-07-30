"""``log`` テーブルへの書き込みハンドラ。

- ``requestId`` はレコード（``RequestContextFilter`` 付与）から取得する。
- DB 未接続・マイグレーション前・書き込み失敗時は黙って諦める
  （ログのために本処理を落とさない）。
- SQLAlchemy 自身のログを書き込むと再帰するため除外する。
"""

from __future__ import annotations

import logging
import traceback as tb_module

import sqlalchemy as sa

_EXCLUDED_LOGGER_PREFIXES = ("sqlalchemy", "alembic", "shared.kernel.logging")


class DbLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_EXCLUDED_LOGGER_PREFIXES):
            return
        try:
            from shared.kernel.settings.settings import settings

            if not settings.log_to_database:
                return
            self._insert(record)
        except Exception:
            pass

    def _insert(self, record: logging.LogRecord) -> None:
        from shared.infrastructure.models.base import utcnow
        from shared.infrastructure.models.log import Log
        from shared.kernel.database.db import get_engine

        trace = None
        if record.exc_info and record.exc_info[0] is not None:
            trace = "".join(tb_module.format_exception(*record.exc_info))

        # duration_ms 列は Integer。SQLite は型アフィニティで float をそのまま
        # 保持してしまうため、書き込み前に丸めて両バックエンドの挙動を揃える。
        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            duration_ms = round(float(duration_ms))

        row = {
            "created_at": utcnow(),
            "level": record.levelname,
            "logger": record.name[:120],
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id_hash": getattr(record, "user_id_hash", None),
            "path": getattr(record, "path", None),
            "method": getattr(record, "method", None),
            "status_code": getattr(record, "status_code", None),
            "duration_ms": duration_ms,
            "trace": trace,
        }
        with get_engine().begin() as connection:
            connection.execute(sa.insert(Log).values(**row))


__all__ = ["DbLogHandler"]
