"""構造化ログ設定（JSON を stdout へ、同時に DB へ書き込み）。

ログには PII を含めない。ユーザー識別子は ``user.id_hash`` のみ
（CLAUDE.md「ログ」参照）。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from shared.kernel.logging.request_context import (
    current_request_id,
    current_user_id_hash,
)
from shared.kernel.timestamps import isoformat_utc

_STDLIB_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class RequestContextFilter(logging.Filter):
    """全レコードへ ``requestId``・``user.id_hash`` を付与する。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        if not hasattr(record, "user_id_hash"):
            record.user_id_hash = current_user_id_hash()
        return True


class StructuredFormatter(logging.Formatter):
    """レコードを1行 JSON に整形する。extra はそのままフィールドになる。"""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        log: dict[str, Any] = {
            "timestamp": isoformat_utc(datetime.now(UTC)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        for key, val in record.__dict__.items():
            if key not in _STDLIB_ATTRS and not key.startswith("_") and val is not None:
                log[key] = val
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", database: bool = True) -> None:
    """ルートロガーへ JSON コンソール出力と DB 書き込みを設定する。"""
    from shared.kernel.logging.db_log_handler import DbLogHandler

    context_filter = RequestContextFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(StructuredFormatter())
    console.addFilter(context_filter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(console)

    if database:
        db_handler = DbLogHandler()
        db_handler.addFilter(context_filter)
        root.addHandler(db_handler)

    # uvicorn の標準アクセスログは抑止する（ミドルウェアで記録する）
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


__all__ = ["RequestContextFilter", "StructuredFormatter", "setup_logging"]
