"""notification の ``Depends()`` 用の組み立て（具象はここだけで選ぶ）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session

from bounded_contexts.notification.application.dto.notification_dto import SendResultDTO
from bounded_contexts.notification.application.use_cases.deliver_push_notification import DeliverPushNotification
from bounded_contexts.notification.application.use_cases.send_notification import (
    SendNotification,
    SendNotificationCommand,
)
from bounded_contexts.notification.domain.services.push_sender import DevicePushSender, PushChannels, PushSender
from bounded_contexts.notification.infrastructure.fcm_sender import FcmSender
from bounded_contexts.notification.infrastructure.sql_device_token_repository import SqlDeviceTokenRepository
from bounded_contexts.notification.infrastructure.sql_notification_repository import SqlNotificationRepository
from bounded_contexts.notification.infrastructure.sql_push_subscription_repository import (
    SqlPushSubscriptionRepository,
)
from bounded_contexts.notification.infrastructure.sql_recipient_directory import SqlRecipientDirectory
from bounded_contexts.notification.infrastructure.web_push_sender import WebPushSender
from shared.kernel.database.db import get_session_factory
from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

DbDep = Annotated[Session, Depends(get_db)]


def get_push_sender() -> PushSender:
    """設定はリクエストのたびに読む（管理画面で鍵の場所を変えたら次から効く）。"""
    return WebPushSender.from_settings()


def get_device_push_sender() -> DevicePushSender:
    """スマホアプリへの送り口（FCM。ADR-0049）。設定はリクエストのたびに読む。"""
    return FcmSender.from_settings()


def get_notification_repository(db: DbDep) -> SqlNotificationRepository:
    return SqlNotificationRepository(db)


def get_recipient_directory(db: DbDep) -> SqlRecipientDirectory:
    return SqlRecipientDirectory(db)


def get_push_subscription_repository(db: DbDep) -> SqlPushSubscriptionRepository:
    return SqlPushSubscriptionRepository(db)


PushSenderDep = Annotated[PushSender, Depends(get_push_sender)]
DevicePushSenderDep = Annotated[DevicePushSender, Depends(get_device_push_sender)]
NotificationRepoDep = Annotated[SqlNotificationRepository, Depends(get_notification_repository)]
RecipientDirectoryDep = Annotated[SqlRecipientDirectory, Depends(get_recipient_directory)]
PushSubscriptionRepoDep = Annotated[SqlPushSubscriptionRepository, Depends(get_push_subscription_repository)]


def get_device_token_repository(db: DbDep) -> SqlDeviceTokenRepository:
    return SqlDeviceTokenRepository(db)


DeviceTokenRepoDep = Annotated[SqlDeviceTokenRepository, Depends(get_device_token_repository)]


def get_push_channels(web: PushSenderDep, device: DevicePushSenderDep) -> PushChannels:
    return PushChannels(web=web, device=device)


PushChannelsDep = Annotated[PushChannels, Depends(get_push_channels)]


def deliver_push_after_response(result: SendResultDTO, channels: PushChannels) -> None:
    """応答を返した後で端末へ送る（``BackgroundTasks`` から呼ぶ）。

    ⚠ **リクエストのセッションは使えない。** FastAPI は ``yield`` の依存（``get_db``）を
    背景の仕事より先に閉じる。ここで自分のセッションを開いて閉じる。
    ⚠ 失敗しても誰にも返せない（応答は返した後）ので、記録だけ残す。
    """
    session = get_session_factory()()
    try:
        DeliverPushNotification(
            SqlPushSubscriptionRepository(session), SqlDeviceTokenRepository(session), channels
        ).execute(result.notification, result.recipient_user_ids)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(
            "notification_push_crashed",
            extra={"event": "notification.push.crashed", "notification_id": result.notification.id},
        )
    finally:
        session.close()


class SendAndDeliverPush:
    """送る（同じトランザクション）→ ``push`` なら応答の後で端末へ届ける、の組。"""

    def __init__(self, use_case: SendNotification, channels: PushChannels, background: BackgroundTasks) -> None:
        self._use_case = use_case
        self._channels = channels
        self._background = background

    def execute(self, command: SendNotificationCommand, now: datetime) -> SendResultDTO:
        result = self._use_case.execute(command, now)
        if result.push_scheduled:
            self._background.add_task(deliver_push_after_response, result, self._channels)
        return result


def get_send_and_deliver_push(
    repo: NotificationRepoDep,
    recipients: RecipientDirectoryDep,
    channels: PushChannelsDep,
    background: BackgroundTasks,
) -> SendAndDeliverPush:
    return SendAndDeliverPush(SendNotification(repo, recipients, channels), channels, background)


SendAndDeliverPushDep = Annotated[SendAndDeliverPush, Depends(get_send_and_deliver_push)]


__all__ = [
    "DevicePushSenderDep",
    "DeviceTokenRepoDep",
    "NotificationRepoDep",
    "PushSenderDep",
    "PushSubscriptionRepoDep",
    "RecipientDirectoryDep",
    "SendAndDeliverPushDep",
    "deliver_push_after_response",
    "get_device_push_sender",
    "get_push_sender",
]
