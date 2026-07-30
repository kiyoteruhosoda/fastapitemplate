"""監査ログ閲覧の DTO（Application → Presentation）。

時刻は ISO 8601（UTC）の文字列へ揃える。Presentation が日時整形の判断をしない
ようにするため。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditLogEntryDto:
    id: int
    occurred_at: str
    event_type: str
    result: str
    actor_user_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class AuditLogPageDto:
    entries: tuple[AuditLogEntryDto, ...] = field(default_factory=tuple)
    total: int = 0


@dataclass(frozen=True)
class AuditLogFilterOptionsDto:
    """絞り込みの選択肢（画面のセレクトボックスを組む材料）。"""

    event_types: tuple[str, ...] = field(default_factory=tuple)
    results: tuple[str, ...] = field(default_factory=tuple)
    target_types: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["AuditLogEntryDto", "AuditLogFilterOptionsDto", "AuditLogPageDto"]
