"""notification API schemas (ADR-0081 §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bounded_contexts.notification.application.dto.notification_dto import (
    InboxEntryDTO,
    NotificationDTO,
    SentNotificationDTO,
)
from shared.kernel.timestamps import isoformat_utc

ChannelName = Literal["bell", "banner", "push"]
AudienceKindName = Literal["all", "group", "user"]


class AudienceRequest(BaseModel):
    kind: AudienceKindName
    #: Target ID for ``group`` / ``user``. Empty for ``all``.
    target_id: int | None = None


class AudienceResponse(AudienceRequest):
    pass


class NotificationResponse(BaseModel):
    id: int
    title: str
    body: str
    link_url: str | None
    channels: list[ChannelName]
    sent_at: str

    @classmethod
    def of(cls, dto: NotificationDTO) -> NotificationResponse:
        return cls(
            id=dto.id,
            title=dto.title,
            body=dto.body,
            link_url=dto.link_url,
            channels=list(dto.channels),  # type: ignore[arg-type]
            sent_at=isoformat_utc(dto.sent_at),
        )


class InboxItemResponse(NotificationResponse):
    read_at: str | None
    dismissed_at: str | None

    @classmethod
    def of_entry(cls, entry: InboxEntryDTO) -> InboxItemResponse:
        base = NotificationResponse.of(entry.notification)
        return cls(
            **base.model_dump(),
            read_at=isoformat_utc(entry.read_at) if entry.read_at else None,
            dismissed_at=isoformat_utc(entry.dismissed_at) if entry.dismissed_at else None,
        )


class InboxResponse(BaseModel):
    items: list[InboxItemResponse]
    #: Count shown on the bell (includes ``bell`` and not yet read).
    unread_count: int


class PushConfigResponse(BaseModel):
    #: Whether device notifications are configured. If false, the UI hides the subscribe controls.
    enabled: bool
    #: Public key (base64url) passed to the browser's ``pushManager.subscribe``.
    public_key: str | None
    #: Whether mobile app notifications (FCM) are configured (ADR-0081 §5).
    #: If false, the app does not register a token.
    device_enabled: bool = False


class PushKeysRequest(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscribeRequest(BaseModel):
    """Accepts the shape of the browser's ``PushSubscription.toJSON()`` as is."""

    endpoint: str = Field(min_length=1, max_length=1000)
    keys: PushKeysRequest


class PushEndpointRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


class DeviceRegisterRequest(BaseModel):
    """FCM registration token the app sends on every launch and sign-in (ADR-0081 §5)."""

    token: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="android", max_length=16)


class DeviceUnregisterRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class PushStatusResponse(BaseModel):
    #: Whether this device's subscription is registered to the current user.
    subscribed: bool


class SendNotificationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    link_url: str | None = Field(default=None, max_length=1000)
    channels: list[ChannelName] = Field(min_length=1)
    audience: AudienceRequest


class SendNotificationResponse(BaseModel):
    notification: NotificationResponse
    audience: AudienceResponse
    recipient_count: int
    push_scheduled: bool


class SentNotificationResponse(BaseModel):
    notification: NotificationResponse
    audience: AudienceResponse
    recipient_count: int
    read_count: int

    @classmethod
    def of(cls, dto: SentNotificationDTO) -> SentNotificationResponse:
        return cls(
            notification=NotificationResponse.of(dto.notification),
            audience=AudienceResponse(
                kind=dto.notification.audience_kind,  # type: ignore[arg-type]
                target_id=dto.notification.audience_target_id,
            ),
            recipient_count=dto.recipient_count,
            read_count=dto.read_count,
        )


class AudienceGroupResponse(BaseModel):
    id: int
    name: str
    member_count: int


class AudienceUserResponse(BaseModel):
    id: int
    username: str
    #: Not returned to senders without ``user:manage`` (nolumiatask #785)
    email: str | None


class AudienceOptionsResponse(BaseModel):
    """Possible audience targets (groups and active users)."""

    groups: list[AudienceGroupResponse]
    users: list[AudienceUserResponse]
