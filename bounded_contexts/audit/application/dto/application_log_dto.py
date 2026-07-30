"""アプリログ閲覧の DTO（Application → Presentation）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApplicationLogEntryDto:
    id: int
    created_at: str
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
class ApplicationLogPageDto:
    entries: tuple[ApplicationLogEntryDto, ...] = field(default_factory=tuple)
    total: int = 0


@dataclass(frozen=True)
class ApplicationLogFilterOptionsDto:
    """絞り込みの選択肢（画面のセレクトボックスを組む材料）。"""

    levels: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "ApplicationLogEntryDto",
    "ApplicationLogFilterOptionsDto",
    "ApplicationLogPageDto",
]
