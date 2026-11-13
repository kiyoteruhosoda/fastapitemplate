"""API schemas of the audit context (log viewing).

Search criteria are gathered into one ``XxxRequest`` and received from the query string. The
limits refer to the Domain :mod:`~bounded_contexts.audit.domain.value_objects.log_page`; the
numbers are not copied here.

**External input is normalized here.** Screen forms send empty strings even for blank fields, so
whitespace is stripped and empty strings are turned into "not specified" (``None``). Only
validated values are passed to the Application layer ("API design" in CLAUDE.md).

Search results come with ``total``, so the screen can show whether paging is possible and the
total count (``entries`` alone cannot tell "is there a next page").
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from bounded_contexts.audit.domain.value_objects.log_page import MAX_LIMIT


def _blank_to_none(value: object) -> object:
    """Strip surrounding whitespace and turn empty strings into "not specified"."""
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    return trimmed or None


def _upper_or_none(value: object) -> object:
    """Uppercase the level name (so ``error`` matches too)."""
    normalized = _blank_to_none(value)
    return normalized.upper() if isinstance(normalized, str) else normalized


# String filter fields. Not used as a condition when sent blank.
FilterText = Annotated[str | None, BeforeValidator(_blank_to_none)]
LevelFilter = Annotated[str | None, BeforeValidator(_upper_or_none)]


class AuditLogSearchRequest(BaseModel):
    """Audit log search criteria (query string). Unspecified fields are not used for filtering."""

    event_type: FilterText = None
    result: FilterText = None
    actor_user_id: int | None = None
    target_type: FilterText = None
    target_id: FilterText = None
    request_id: FilterText = None
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
    """Total count matching the criteria, and one page of it."""

    total: int
    entries: list[AuditLogEntryResponse]


class AuditLogFilterOptionsResponse(BaseModel):
    """Filter choices (a list so the enums need not be copied to the frontend)."""

    event_types: list[str]
    results: list[str]
    target_types: list[str]


class LogSearchRequest(BaseModel):
    """Application log search criteria (query string)."""

    level: LevelFilter = None
    logger: FilterText = Field(default=None, description="ロガー名の前方一致")
    message: FilterText = Field(default=None, description="メッセージ本文の部分一致")
    request_id: FilterText = None
    user_id_hash: FilterText = None
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
