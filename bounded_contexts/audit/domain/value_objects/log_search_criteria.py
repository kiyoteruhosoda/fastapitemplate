"""Log search criteria (audit logs and application logs).

Only the given fields (those not ``None``) are stacked with **AND**.

**Received values are assumed normalized.** Screen forms send empty strings even for blank
fields, but rounding external input such as "empty string means unspecified" and "level names
in uppercase" is done by the Presentation layer's ``XxxRequest`` ("API design" in CLAUDE.md:
only validated values are passed to the Application layer). An empty string that reaches here
means "find rows equal to the empty string".

Audit logs and application logs filter on different axes, but the construction "bound by a
period, take one page newest first" is the same, so they live in the same module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from bounded_contexts.audit.domain.value_objects.log_page import LogPage


class LogLevel(StrEnum):
    """Values that can appear in ``log.level`` (Python standard logging level names).

    The source of truth for sharing filter choices with the screen. Stored rows may hold values not
    in this enum, so the reading side treats them as strings.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AuditLogCriteria:
    """Audit log search criteria.

    ``result="failure"`` extracts only failed operations, and ``request_id`` only the events of one
    request.
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
    """Application log search criteria.

    ``logger_prefix`` is a prefix match on the logger name (``app.request`` for HTTP access logs
    only, ``bounded_contexts`` for business processing only). ``message_contains`` is a substring
    match on the message.
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
