"""Interface for sending device notifications (implemented in the Infrastructure layer).

There are two senders: Web Push to browsers/PWAs (:class:`PushSender`; ADR-0081 §3) and
FCM to the mobile app (:class:`DevicePushSender`; ADR-0081 §5). A notification with ``push``
goes to both (:class:`PushChannels`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from bounded_contexts.notification.domain.entities.device_token import DeviceToken
from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription


class PushOutcome(StrEnum):
    DELIVERED = "delivered"
    #: The push service said the subscription is gone (404 / 410). Remove the subscription.
    GONE = "gone"
    #: Any other failure. Keep the subscription (the push service may be having a temporary problem).
    FAILED = "failed"


@dataclass(frozen=True)
class PushMessage:
    """Payload handed to the device. The Service Worker reads it and shows the notification."""

    notification_id: int
    title: str
    body: str
    link_url: str | None


class PushSender(ABC):
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether sending is configured (false without a key)."""

    @abstractmethod
    def public_key(self) -> str | None:
        """Public key (base64url) for browser subscriptions. ``None`` if sending is not configured."""

    @abstractmethod
    def send(self, subscription: PushSubscription, message: PushMessage) -> PushOutcome: ...


class DevicePushSender(ABC):
    """Mobile app notifications (FCM)."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether sending is configured (false without a service account key)."""

    @abstractmethod
    def send(self, device: DeviceToken, message: PushMessage) -> PushOutcome: ...


@dataclass(frozen=True)
class PushChannels:
    """The set of senders for notifications that chose ``push``."""

    web: PushSender
    device: DevicePushSender

    @property
    def enabled(self) -> bool:
        """``push`` can be chosen if at least one of them can send."""
        return self.web.enabled or self.device.enabled
