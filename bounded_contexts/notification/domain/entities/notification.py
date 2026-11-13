"""A single notification (ADR-0081 §3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.notification.domain.exceptions import NotificationValidationError
from bounded_contexts.notification.domain.value_objects.audience import Audience
from bounded_contexts.notification.domain.value_objects.channel import NotificationChannel
from bounded_contexts.notification.domain.value_objects.content import NotificationContent


@dataclass(frozen=True)
class Notification:
    #: ``None`` until saved.
    id: int | None
    content: NotificationContent
    channels: frozenset[NotificationChannel]
    audience: Audience
    #: The admin who sent it. Stays as an ID even if the user is deleted.
    sender_user_id: int | None
    sent_at: datetime

    def __post_init__(self) -> None:
        if not self.channels:
            raise NotificationValidationError("channel_required")


@dataclass(frozen=True)
class InboxEntry:
    """One notification as held by a given user (with read/dismissed state)."""

    notification: Notification
    read_at: datetime | None
    dismissed_at: datetime | None


@dataclass(frozen=True)
class SentNotification:
    """Sent record (admin console history): how many it was delivered to and how many read it."""

    notification: Notification
    recipient_count: int
    read_count: int
