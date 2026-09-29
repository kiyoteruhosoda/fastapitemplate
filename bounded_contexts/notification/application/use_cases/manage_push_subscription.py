"""端末への通知の宛先を登録・解除する（ブラウザの購読と、スマホアプリのトークン）。"""

from __future__ import annotations

from bounded_contexts.notification.domain.entities.device_token import DeviceToken
from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription
from bounded_contexts.notification.domain.exceptions import NotificationValidationError
from bounded_contexts.notification.domain.repositories.device_token_repository import IDeviceTokenRepository
from bounded_contexts.notification.domain.repositories.push_subscription_repository import (
    IPushSubscriptionRepository,
)
from bounded_contexts.notification.domain.services.push_sender import DevicePushSender, PushSender

#: 通知サービスの endpoint は数百文字。これを超えるものは購読として受け取らない。
ENDPOINT_MAX_LENGTH = 1000
#: FCM の登録トークンは 150〜200 文字程度。これを超えるものは受け取らない。
DEVICE_TOKEN_MAX_LENGTH = 4096
#: 受け付ける端末の種類。
DEVICE_PLATFORMS = frozenset({"android"})
#: 鍵は base64url で p256dh が 87 文字・auth が 22 文字。余裕を見て切る。
KEY_MAX_LENGTH = 255


class SubscribeToPush:
    def __init__(self, subscriptions: IPushSubscriptionRepository, sender: PushSender) -> None:
        self._subscriptions = subscriptions
        self._sender = sender

    def execute(self, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
        if not self._sender.enabled:
            raise NotificationValidationError("push_not_configured")
        # ⚠ endpoint はこのサーバーが POST しに行く先。https 以外を受けると、
        #   利用者がサーバーに内側の URL を叩かせられる。
        if not endpoint.startswith("https://") or len(endpoint) > ENDPOINT_MAX_LENGTH:
            raise NotificationValidationError("invalid_push_endpoint")
        if not (0 < len(p256dh) <= KEY_MAX_LENGTH and 0 < len(auth) <= KEY_MAX_LENGTH):
            raise NotificationValidationError("invalid_push_keys")
        self._subscriptions.save(PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth))


class UnsubscribeFromPush:
    def __init__(self, subscriptions: IPushSubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    def execute(self, user_id: int, endpoint: str) -> None:
        self._subscriptions.remove(user_id, endpoint)


class RegisterDevice:
    """スマホアプリの FCM の登録トークンを預かる（ADR-0049）。"""

    def __init__(self, devices: IDeviceTokenRepository, sender: DevicePushSender) -> None:
        self._devices = devices
        self._sender = sender

    def execute(self, user_id: int, token: str, platform: str) -> None:
        if not self._sender.enabled:
            raise NotificationValidationError("device_push_not_configured")
        token = token.strip()
        if not token or len(token) > DEVICE_TOKEN_MAX_LENGTH:
            raise NotificationValidationError("invalid_device_token")
        if platform not in DEVICE_PLATFORMS:
            raise NotificationValidationError("unknown_platform")
        self._devices.save(DeviceToken(user_id=user_id, token=token, platform=platform))


class UnregisterDevice:
    def __init__(self, devices: IDeviceTokenRepository) -> None:
        self._devices = devices

    def execute(self, user_id: int, token: str) -> None:
        self._devices.remove(user_id, token.strip())
