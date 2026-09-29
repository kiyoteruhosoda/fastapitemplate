"""お知らせ 1 通（ADR-0047）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.notification.domain.exceptions import NotificationValidationError
from bounded_contexts.notification.domain.value_objects.audience import Audience
from bounded_contexts.notification.domain.value_objects.channel import NotificationChannel
from bounded_contexts.notification.domain.value_objects.content import NotificationContent


@dataclass(frozen=True)
class Notification:
    #: 保存するまでは ``None``。
    id: int | None
    content: NotificationContent
    channels: frozenset[NotificationChannel]
    audience: Audience
    #: 送った管理者。利用者を消しても ID のまま残る。
    sender_user_id: int | None
    sent_at: datetime

    def __post_init__(self) -> None:
        if not self.channels:
            raise NotificationValidationError("channel_required")


@dataclass(frozen=True)
class InboxEntry:
    """ある利用者の手元にある 1 通（既読・閉じたかを持つ）。"""

    notification: Notification
    read_at: datetime | None
    dismissed_at: datetime | None


@dataclass(frozen=True)
class SentNotification:
    """送った記録（管理画面の履歴）。何人に配り、何人が読んだか。"""

    notification: Notification
    recipient_count: int
    read_count: int
