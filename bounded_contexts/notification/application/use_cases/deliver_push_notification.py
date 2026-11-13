"""Deliver a sent notification to the recipients' devices (ADR-0081 §3 / ADR-0081 §5).

There are two kinds of targets: browser/PWA subscriptions (Web Push) and mobile app tokens (FCM).
Send only to those that are configured.

⚠ **One device's failure does not stop the rest.** Targets the push service reports as gone
(browser data cleared or app uninstalled) are removed here. Other failures keep the target
and are only counted (so a temporary push service problem doesn't lose targets).
"""

from __future__ import annotations

import logging
from collections import Counter

from bounded_contexts.notification.application.dto.notification_dto import (
    NotificationDTO,
    PushReportDTO,
)
from bounded_contexts.notification.domain.repositories.device_token_repository import IDeviceTokenRepository
from bounded_contexts.notification.domain.repositories.push_subscription_repository import (
    IPushSubscriptionRepository,
)
from bounded_contexts.notification.domain.services.push_sender import (
    PushChannels,
    PushMessage,
    PushOutcome,
)

logger = logging.getLogger(__name__)


class DeliverPushNotification:
    def __init__(
        self,
        subscriptions: IPushSubscriptionRepository,
        devices: IDeviceTokenRepository,
        channels: PushChannels,
    ) -> None:
        self._subscriptions = subscriptions
        self._devices = devices
        self._channels = channels

    def execute(self, notification: NotificationDTO, recipient_user_ids: tuple[int, ...]) -> PushReportDTO:
        message = PushMessage(
            notification_id=notification.id,
            title=notification.title,
            body=notification.body,
            link_url=notification.link_url,
        )
        recipients = list(recipient_user_ids)
        counts: Counter[PushOutcome] = Counter()
        if self._channels.web.enabled:
            counts.update(self._to_browsers(recipients, message))
        if self._channels.device.enabled:
            counts.update(self._to_apps(recipients, message))
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

    def _to_browsers(self, recipients: list[int], message: PushMessage) -> list[PushOutcome]:
        outcomes = []
        for subscription in self._subscriptions.for_users(recipients):
            outcome = self._channels.web.send(subscription, message)
            if outcome is PushOutcome.GONE:
                self._subscriptions.remove_endpoint(subscription.endpoint)
            outcomes.append(outcome)
        return outcomes

    def _to_apps(self, recipients: list[int], message: PushMessage) -> list[PushOutcome]:
        outcomes = []
        for device in self._devices.for_users(recipients):
            outcome = self._channels.device.send(device, message)
            if outcome is PushOutcome.GONE:
                self._devices.remove_token(device.token)
            outcomes.append(outcome)
        return outcomes
