"""送ったお知らせを、宛先の人が購読している端末へ届ける（ADR-0047）。

⚠ **1 台の失敗で残りを止めない。** 通知サービスが「もう無い」と答えた購読
（端末でブラウザのデータを消した・通知を切った）はここで外す。それ以外の失敗は
購読を残して数えるだけにする（通知サービスの一時的な不調で購読を失わない）。
"""

from __future__ import annotations

import logging

from bounded_contexts.notification.application.dto.notification_dto import (
    NotificationDTO,
    PushReportDTO,
)
from bounded_contexts.notification.domain.repositories.push_subscription_repository import (
    IPushSubscriptionRepository,
)
from bounded_contexts.notification.domain.services.push_sender import (
    PushMessage,
    PushOutcome,
    PushSender,
)

logger = logging.getLogger(__name__)


class DeliverPushNotification:
    def __init__(self, subscriptions: IPushSubscriptionRepository, sender: PushSender) -> None:
        self._subscriptions = subscriptions
        self._sender = sender

    def execute(self, notification: NotificationDTO, recipient_user_ids: tuple[int, ...]) -> PushReportDTO:
        message = PushMessage(
            notification_id=notification.id,
            title=notification.title,
            body=notification.body,
            link_url=notification.link_url,
        )
        counts = dict.fromkeys(PushOutcome, 0)
        for subscription in self._subscriptions.for_users(list(recipient_user_ids)):
            outcome = self._sender.send(subscription, message)
            counts[outcome] += 1
            if outcome is PushOutcome.GONE:
                self._subscriptions.remove_endpoint(subscription.endpoint)
        report = PushReportDTO(
            delivered=counts[PushOutcome.DELIVERED],
            gone=counts[PushOutcome.GONE],
            failed=counts[PushOutcome.FAILED],
        )
        logger.info(
            "notification_push_delivered",
            extra={
                "event": "notification.push.delivered",
                "notification_id": notification.id,
                "delivered": report.delivered,
                "gone": report.gone,
                "failed": report.failed,
            },
        )
        return report
