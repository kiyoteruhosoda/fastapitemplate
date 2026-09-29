"""お知らせを送る（ADR-0047）。

1. 中身を検証してお知らせを作る
2. 宛先を**いまの顔ぶれ**へ展開し、1 人ずつに配る（同じトランザクション）
3. ``push`` を選んでいれば、端末へ送るのは呼び出し側が**応答の後で**行う
   （:class:`DeliverPushNotification`）。通知サービスへの往復は相手の数だけかかり、
   管理画面を待たせる理由が無い
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.notification.application.dto.notification_dto import (
    NotificationDTO,
    SendResultDTO,
)
from bounded_contexts.notification.domain.entities.notification import Notification
from bounded_contexts.notification.domain.exceptions import NotificationValidationError
from bounded_contexts.notification.domain.repositories.notification_repository import INotificationRepository
from bounded_contexts.notification.domain.repositories.recipient_directory import IRecipientDirectory
from bounded_contexts.notification.domain.services.push_sender import PushChannels
from bounded_contexts.notification.domain.value_objects.audience import Audience, AudienceKind
from bounded_contexts.notification.domain.value_objects.channel import NotificationChannel
from bounded_contexts.notification.domain.value_objects.content import NotificationContent


@dataclass(frozen=True)
class SendNotificationCommand:
    title: str
    body: str
    link_url: str | None
    channels: tuple[str, ...]
    audience_kind: str
    audience_target_id: int | None
    sender_user_id: int | None


def _channels(values: tuple[str, ...]) -> frozenset[NotificationChannel]:
    try:
        return frozenset(NotificationChannel(v) for v in values)
    except ValueError as exc:
        raise NotificationValidationError("unknown_channel") from exc


def _audience(kind: str, target_id: int | None) -> Audience:
    try:
        audience_kind = AudienceKind(kind)
    except ValueError as exc:
        raise NotificationValidationError("unknown_audience") from exc
    return Audience(audience_kind, target_id)


class SendNotification:
    def __init__(
        self,
        notifications: INotificationRepository,
        recipients: IRecipientDirectory,
        push: PushChannels,
    ) -> None:
        self._notifications = notifications
        self._recipients = recipients
        self._push = push

    def execute(self, command: SendNotificationCommand, now: datetime) -> SendResultDTO:
        channels = _channels(command.channels)
        if NotificationChannel.PUSH in channels and not self._push.enabled:
            # 選べてしまうと「送った」のに誰にも届かない。画面は選ばせないが、API も断る。
            raise NotificationValidationError("push_not_configured")
        notification = Notification(
            id=None,
            content=NotificationContent.of(command.title, command.body, command.link_url),
            channels=channels,
            audience=_audience(command.audience_kind, command.audience_target_id),
            sender_user_id=command.sender_user_id,
            sent_at=now,
        )
        recipient_ids = self._recipients.resolve(notification.audience)
        if not recipient_ids:
            raise NotificationValidationError("no_recipients")
        saved = self._notifications.add(notification, recipient_ids)
        return SendResultDTO(
            notification=NotificationDTO.of(saved),
            recipient_user_ids=tuple(recipient_ids),
            push_scheduled=NotificationChannel.PUSH in channels,
        )
