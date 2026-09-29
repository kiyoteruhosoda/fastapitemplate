"""利用者の手元のお知らせ（ベルと画面上部）を読む・既読にする・閉じる。"""

from __future__ import annotations

from datetime import datetime

from bounded_contexts.notification.application.dto.notification_dto import InboxDTO, InboxEntryDTO
from bounded_contexts.notification.domain.exceptions import NotificationNotFoundError
from bounded_contexts.notification.domain.repositories.notification_repository import INotificationRepository

#: ベルの一覧に出す件数の上限。古いものは一覧から落ちるだけで消えはしない。
INBOX_LIMIT = 50


class ListInbox:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: int) -> InboxDTO:
        entries = self._notifications.inbox(user_id, limit=INBOX_LIMIT)
        return InboxDTO(
            entries=tuple(InboxEntryDTO.of(e) for e in entries),
            unread_count=self._notifications.unread_count(user_id),
        )


class MarkNotificationRead:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: int, notification_id: int, now: datetime) -> None:
        if not self._notifications.mark_read(user_id, notification_id, now):
            raise NotificationNotFoundError(notification_id)


class MarkAllNotificationsRead:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: int, now: datetime) -> None:
        self._notifications.mark_all_read(user_id, now)


class DismissNotification:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: int, notification_id: int, now: datetime) -> None:
        if not self._notifications.dismiss(user_id, notification_id, now):
            raise NotificationNotFoundError(notification_id)
