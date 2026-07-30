"""ログ検索条件（監査ログ・アプリログ）。

指定された項目（``None`` でない項目）だけを **AND** で積む。

**受け取る値は正規化済み**とする。画面のフォームは未入力の項目も空文字で送ってくるが、
「空文字は未指定」「レベル名は大文字」といった外部入力の丸めは Presentation 層の
``〇〇Request`` が行う（CLAUDE.md「API 設計」: Application 層へはバリデーション済みの
値のみを渡す）。ここまで来た空文字は「空文字に一致する行を探せ」の意味になる。

監査ログとアプリログで条件の軸は違うが、「期間で挟む」「新しい順に 1 ページ取る」
という組み立ては同じなので同じモジュールに置く。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from bounded_contexts.audit.domain.value_objects.log_page import LogPage


class LogLevel(StrEnum):
    """``log.level`` に入り得る値（Python 標準ロギングのレベル名）。

    絞り込みの選択肢を画面と共有するための正本。保存済みの行はこの列挙に無い値も
    取り得るため、読み取り側は文字列として扱う。
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AuditLogCriteria:
    """監査ログの検索条件。

    ``result="failure"`` で失敗操作だけを、``request_id`` で 1 リクエスト分の
    イベントだけを取り出せる。
    """

    event_type: str | None = None
    result: str | None = None
    actor_user_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    request_id: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    page: LogPage = field(default_factory=LogPage)


@dataclass(frozen=True)
class ApplicationLogCriteria:
    """アプリログの検索条件。

    ``logger_prefix`` はロガー名の前方一致（``app.request`` で HTTP アクセスログ
    のみ、``bounded_contexts`` で業務処理のみ）。``message_contains`` は本文の
    部分一致。
    """

    level: str | None = None
    logger_prefix: str | None = None
    message_contains: str | None = None
    request_id: str | None = None
    user_id_hash: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: LogPage = field(default_factory=LogPage)


__all__ = ["ApplicationLogCriteria", "AuditLogCriteria", "LogLevel"]
