"""アプリログの読み取りモデル（``log`` テーブル 1 行）。

書き込みは :mod:`shared.kernel.logging` の ``DbLogHandler`` が行う（ログ出力は
全レイヤー横断の関心事なので、記録側は audit コンテキストに属さない）。ここは
**閲覧のためにテーブルを読む側**の型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ApplicationLogEntry:
    """``log`` の 1 行。PII は含まれない（利用者は ``user_id_hash`` のみ）。"""

    id: int
    created_at: datetime
    level: str
    logger: str
    message: str
    request_id: str | None = None
    user_id_hash: str | None = None
    path: str | None = None
    method: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    trace: str | None = None


@dataclass(frozen=True)
class ApplicationLogPage:
    """検索結果 1 ページと、条件に一致する総件数。"""

    entries: tuple[ApplicationLogEntry, ...] = field(default_factory=tuple)
    total: int = 0


__all__ = ["ApplicationLogEntry", "ApplicationLogPage"]
