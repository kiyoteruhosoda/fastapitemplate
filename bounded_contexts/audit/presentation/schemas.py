"""audit コンテキストの API スキーマ（ログ閲覧）。

検索条件は 1 つの ``〇〇Request`` にまとめてクエリ文字列から受け取る。件数上限は
Domain の :mod:`~bounded_contexts.audit.domain.value_objects.log_page` を参照し、
ここに数値を写さない。

検索結果は ``total`` を添えて返す。画面がページ送りの可否と総件数を出せるように
するため（``entries`` だけでは「次があるか」が分からない）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from bounded_contexts.audit.domain.value_objects.log_page import MAX_LIMIT


class AuditLogSearchRequest(BaseModel):
    """監査ログの検索条件（クエリ文字列）。未指定の項目は絞り込みに使わない。"""

    event_type: str | None = None
    result: str | None = None
    actor_user_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    request_id: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    offset: int | None = Field(default=None, ge=0)


class AuditLogEntryResponse(BaseModel):
    id: int
    occurred_at: str
    event_type: str
    result: str
    actor_user_id: int | None
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    user_agent: str | None
    reason: str | None
    request_id: str | None


class AuditLogSearchResponse(BaseModel):
    """条件に一致した総件数と、そのうち 1 ページ分。"""

    total: int
    entries: list[AuditLogEntryResponse]


class AuditLogFilterOptionsResponse(BaseModel):
    """絞り込みの選択肢（列挙をフロントエンドへ写さないための一覧）。"""

    event_types: list[str]
    results: list[str]
    target_types: list[str]


class LogSearchRequest(BaseModel):
    """アプリログの検索条件（クエリ文字列）。"""

    level: str | None = None
    logger: str | None = Field(default=None, description="ロガー名の前方一致")
    message: str | None = Field(default=None, description="メッセージ本文の部分一致")
    request_id: str | None = None
    user_id_hash: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    offset: int | None = Field(default=None, ge=0)


class LogEntryResponse(BaseModel):
    id: int
    created_at: str
    level: str
    logger: str
    message: str
    request_id: str | None
    user_id_hash: str | None
    path: str | None
    method: str | None
    status_code: int | None
    duration_ms: int | None
    trace: str | None


class LogSearchResponse(BaseModel):
    total: int
    entries: list[LogEntryResponse]


class LogFilterOptionsResponse(BaseModel):
    levels: list[str]


__all__ = [
    "AuditLogEntryResponse",
    "AuditLogFilterOptionsResponse",
    "AuditLogSearchRequest",
    "AuditLogSearchResponse",
    "LogEntryResponse",
    "LogFilterOptionsResponse",
    "LogSearchRequest",
    "LogSearchResponse",
]
