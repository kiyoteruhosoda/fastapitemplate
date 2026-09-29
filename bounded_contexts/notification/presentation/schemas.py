"""notification の API スキーマ（ADR-0047）。"""

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


class AudienceSchema(BaseModel):
    kind: AudienceKindName
    #: ``group`` / ``user`` のときの相手の ID。``all`` では空。
    target_id: int | None = None


class NotificationSchema(BaseModel):
    id: int
    title: str
    body: str
    link_url: str | None
    channels: list[ChannelName]
    sent_at: str

    @classmethod
    def of(cls, dto: NotificationDTO) -> NotificationSchema:
        return cls(
            id=dto.id,
            title=dto.title,
            body=dto.body,
            link_url=dto.link_url,
            channels=list(dto.channels),  # type: ignore[arg-type]
            sent_at=isoformat_utc(dto.sent_at),
        )


class InboxItemSchema(NotificationSchema):
    read_at: str | None
    dismissed_at: str | None

    @classmethod
    def of_entry(cls, entry: InboxEntryDTO) -> InboxItemSchema:
        base = NotificationSchema.of(entry.notification)
        return cls(
            **base.model_dump(),
            read_at=isoformat_utc(entry.read_at) if entry.read_at else None,
            dismissed_at=isoformat_utc(entry.dismissed_at) if entry.dismissed_at else None,
        )


class InboxResponse(BaseModel):
    items: list[InboxItemSchema]
    #: ベルに出す数（``bell`` を含み、まだ読んでいないもの）。
    unread_count: int


class PushConfigResponse(BaseModel):
    #: 端末への通知を出せる設定になっているか。偽なら画面は購読の操作を出さない。
    enabled: bool
    #: ブラウザの ``pushManager.subscribe`` に渡す公開鍵（base64url）。
    public_key: str | None


class PushKeysSchema(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscribeRequest(BaseModel):
    """ブラウザの ``PushSubscription.toJSON()`` の形をそのまま受ける。"""

    endpoint: str = Field(min_length=1, max_length=1000)
    keys: PushKeysSchema


class PushEndpointRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


class PushStatusResponse(BaseModel):
    #: この端末の購読が、いまの利用者のものとして登録されているか。
    subscribed: bool


class SendNotificationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    link_url: str | None = Field(default=None, max_length=1000)
    channels: list[ChannelName] = Field(min_length=1)
    audience: AudienceSchema


class SendNotificationResponse(BaseModel):
    notification: NotificationSchema
    audience: AudienceSchema
    recipient_count: int
    push_scheduled: bool


class SentNotificationResponse(BaseModel):
    notification: NotificationSchema
    audience: AudienceSchema
    recipient_count: int
    read_count: int

    @classmethod
    def of(cls, dto: SentNotificationDTO) -> SentNotificationResponse:
        return cls(
            notification=NotificationSchema.of(dto.notification),
            audience=AudienceSchema(
                kind=dto.notification.audience_kind,  # type: ignore[arg-type]
                target_id=dto.notification.audience_target_id,
            ),
            recipient_count=dto.recipient_count,
            read_count=dto.read_count,
        )


class AudienceGroupSchema(BaseModel):
    id: int
    name: str
    member_count: int


class AudienceUserSchema(BaseModel):
    id: int
    username: str
    email: str


class AudienceOptionsResponse(BaseModel):
    """宛先に選べる相手（グループと、有効な利用者）。"""

    groups: list[AudienceGroupSchema]
    users: list[AudienceUserSchema]
