from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.notification.domain.entities.notification import (
    InboxEntry,
    Notification,
    SentNotification,
)


@dataclass(frozen=True)
class NotificationDTO:
    id: int
    title: str
    body: str
    link_url: str | None
    channels: tuple[str, ...]
    audience_kind: str
    audience_target_id: int | None
    sent_at: datetime

    @classmethod
    def of(cls, notification: Notification) -> NotificationDTO:
        if notification.id is None:
            raise ValueError("a notification must be saved before it becomes a DTO")
        return cls(
            id=notification.id,
            title=notification.content.title,
            body=notification.content.body,
            link_url=notification.content.link_url,
            channels=tuple(sorted(c.value for c in notification.channels)),
            audience_kind=notification.audience.kind.value,
            audience_target_id=notification.audience.target_id,
            sent_at=notification.sent_at,
        )


@dataclass(frozen=True)
class InboxEntryDTO:
    notification: NotificationDTO
    read_at: datetime | None
    dismissed_at: datetime | None

    @classmethod
    def of(cls, entry: InboxEntry) -> InboxEntryDTO:
        return cls(
            notification=NotificationDTO.of(entry.notification),
            read_at=entry.read_at,
            dismissed_at=entry.dismissed_at,
        )


@dataclass(frozen=True)
class InboxDTO:
    entries: tuple[InboxEntryDTO, ...]
    unread_count: int


@dataclass(frozen=True)
class SentNotificationDTO:
    notification: NotificationDTO
    recipient_count: int
    read_count: int

    @classmethod
    def of(cls, sent: SentNotification) -> SentNotificationDTO:
        return cls(
            notification=NotificationDTO.of(sent.notification),
            recipient_count=sent.recipient_count,
            read_count=sent.read_count,
        )


@dataclass(frozen=True)
class SendResultDTO:
    notification: NotificationDTO
    recipient_user_ids: tuple[int, ...]
    #: 端末への通知を送る予定か（``push`` を選んでいる）。
    push_scheduled: bool


@dataclass(frozen=True)
class PushReportDTO:
    delivered: int
    gone: int
    failed: int
