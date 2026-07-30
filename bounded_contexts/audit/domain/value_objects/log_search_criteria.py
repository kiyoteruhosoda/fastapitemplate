"""ログ検索条件（監査ログ・アプリログ）。

指定された項目だけを **AND** で積む。空文字・空白のみの値は「未指定」として扱う
（画面のフォームは未入力の項目も送ってくるため、その正規化をここで一度だけ行う）。

監査ログとアプリログで条件の軸は違うが、「空を未指定に丸める」「期間で挟む」
「新しい順に 1 ページ取る」という組み立ては同じなので同じモジュールに置く。
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


def _normalized(value: str | None) -> str | None:
    """前後の空白を落とし、空文字は「未指定」（``None``）にする。"""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


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

    @classmethod
    def of(
        cls,
        *,
        event_type: str | None = None,
        result: str | None = None,
        actor_user_id: int | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        request_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        page: LogPage | None = None,
    ) -> AuditLogCriteria:
        """外部入力（クエリ文字列）から生成する。空文字は未指定へ丸める。"""
        return cls(
            event_type=_normalized(event_type),
            result=_normalized(result),
            actor_user_id=actor_user_id,
            target_type=_normalized(target_type),
            target_id=_normalized(target_id),
            request_id=_normalized(request_id),
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            page=page or LogPage(),
        )


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

    @classmethod
    def of(
        cls,
        *,
        level: str | None = None,
        logger_prefix: str | None = None,
        message_contains: str | None = None,
        request_id: str | None = None,
        user_id_hash: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        page: LogPage | None = None,
    ) -> ApplicationLogCriteria:
        """外部入力から生成する。レベル名は大文字へ揃える（``error`` も拾う）。"""
        normalized_level = _normalized(level)
        return cls(
            level=normalized_level.upper() if normalized_level else None,
            logger_prefix=_normalized(logger_prefix),
            message_contains=_normalized(message_contains),
            request_id=_normalized(request_id),
            user_id_hash=_normalized(user_id_hash),
            created_from=created_from,
            created_to=created_to,
            page=page or LogPage(),
        )


__all__ = ["ApplicationLogCriteria", "AuditLogCriteria", "LogLevel"]
