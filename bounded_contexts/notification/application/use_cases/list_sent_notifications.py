from __future__ import annotations

from bounded_contexts.notification.application.dto.notification_dto import SentNotificationDTO
from bounded_contexts.notification.domain.repositories.notification_repository import INotificationRepository

#: 管理画面の履歴に出す件数。
SENT_LIMIT = 100


class ListSentNotifications:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    def execute(self) -> list[SentNotificationDTO]:
        return [SentNotificationDTO.of(s) for s in self._notifications.sent(limit=SENT_LIMIT)]
