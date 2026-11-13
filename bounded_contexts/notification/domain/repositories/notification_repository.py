from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from bounded_contexts.notification.domain.entities.notification import (
    InboxEntry,
    Notification,
    SentNotification,
)


class INotificationRepository(ABC):
    @abstractmethod
    def add(self, notification: Notification, recipient_user_ids: list[int]) -> Notification:
        """Save the notification and deliver it to each member of the audience (returns it with its ID)."""

    @abstractmethod
    def inbox(self, user_id: int, *, limit: int) -> list[InboxEntry]:
        """What was delivered to that user (newest first)."""

    @abstractmethod
    def unread_count(self, user_id: int) -> int:
        """Count shown on the bell (includes ``bell`` and not yet read)."""

    @abstractmethod
    def mark_read(self, user_id: int, notification_id: int, at: datetime) -> bool:
        """Mark as read. ``False`` if it is not addressed to that user."""

    @abstractmethod
    def mark_all_read(self, user_id: int, at: datetime) -> None: ...

    @abstractmethod
    def dismiss(self, user_id: int, notification_id: int, at: datetime) -> bool:
        """Dismiss from the top of the screen (also marks as read). ``False`` if it is not addressed to that user."""

    @abstractmethod
    def sent(self, *, limit: int) -> list[SentNotification]:
        """Sent records (newest first)."""
