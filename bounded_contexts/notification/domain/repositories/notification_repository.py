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
        """お知らせを保存し、宛先の 1 人ずつに配る（ID を振ったものを返す）。"""

    @abstractmethod
    def inbox(self, user_id: int, *, limit: int) -> list[InboxEntry]:
        """その利用者に配られたもの（新しい順）。"""

    @abstractmethod
    def unread_count(self, user_id: int) -> int:
        """ベルに出る数（``bell`` を含み、まだ読んでいないもの）。"""

    @abstractmethod
    def mark_read(self, user_id: int, notification_id: int, at: datetime) -> bool:
        """既読にする。その人宛てでなければ ``False``。"""

    @abstractmethod
    def mark_all_read(self, user_id: int, at: datetime) -> None: ...

    @abstractmethod
    def dismiss(self, user_id: int, notification_id: int, at: datetime) -> bool:
        """画面上部から閉じる（既読にもする）。その人宛てでなければ ``False``。"""

    @abstractmethod
    def sent(self, *, limit: int) -> list[SentNotification]:
        """送った記録（新しい順）。"""
