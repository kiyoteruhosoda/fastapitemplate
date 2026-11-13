"""DTOs for viewing audit logs (Application -> Presentation).

Times are normalized to ISO 8601 (UTC) strings so that Presentation does not make date
formatting decisions.
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
    """Filter choices (material for building the screen's select boxes)."""

    event_types: tuple[str, ...] = field(default_factory=tuple)
    results: tuple[str, ...] = field(default_factory=tuple)
    target_types: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["AuditLogEntryDto", "AuditLogFilterOptionsDto", "AuditLogPageDto"]
