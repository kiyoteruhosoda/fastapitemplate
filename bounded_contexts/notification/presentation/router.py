"""お知らせの API（ADR-0047）。

- ``/api/notifications`` —— 本人の手元（ベル・画面上部）と、端末への通知の購読。
  **アプリからも叩いてよい**（:data:`AppOrWebPrincipalDep`。ADR-0045）ので、スマホアプリも
  同じ口でベルと上部の知らせを出せる。scope は要求しない（自分宛てのものしか見えない）
- ``/api/admin/notifications`` —— 管理画面からの配信と履歴（``notification:send``）
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.presentation.app_bearer import AppOrWebPrincipalDep
from bounded_contexts.notification.application.dto.notification_dto import SendResultDTO
from bounded_contexts.notification.application.use_cases.list_sent_notifications import ListSentNotifications
from bounded_contexts.notification.application.use_cases.manage_inbox import (
    DismissNotification,
    ListInbox,
    MarkAllNotificationsRead,
    MarkNotificationRead,
)
from bounded_contexts.notification.application.use_cases.manage_push_subscription import (
    SubscribeToPush,
    UnsubscribeFromPush,
)
from bounded_contexts.notification.application.use_cases.send_notification import SendNotificationCommand
from bounded_contexts.notification.presentation.dependencies import (
    DbDep,
    NotificationRepoDep,
    PushSenderDep,
    PushSubscriptionRepoDep,
    SendAndDeliverPushDep,
)
from bounded_contexts.notification.presentation.schemas import (
    AudienceGroupSchema,
    AudienceOptionsResponse,
    AudienceSchema,
    AudienceUserSchema,
    InboxItemSchema,
    InboxResponse,
    NotificationSchema,
    PushConfigResponse,
    PushEndpointRequest,
    PushStatusResponse,
    PushSubscribeRequest,
    SendNotificationRequest,
    SendNotificationResponse,
    SentNotificationResponse,
)
from presentation.fastapi.dependencies.auth import require_permission
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User, UserGroup
from shared.kernel.timestamps import utcnow

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
admin_router = APIRouter(prefix="/api/admin/notifications", tags=["admin"])

SenderDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("notification:send"))]

# reason 列は 255 文字。
_MAX_REASON_LENGTH = 255


# --- 本人の手元 -----------------------------------------------------------------


@router.get("", response_model=InboxResponse)
async def list_my_notifications(principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> InboxResponse:
    """ベルと画面上部に出すもの（新しい順）。どこに出すかは ``channels`` で画面が決める。"""
    inbox = ListInbox(repo).execute(principal.user_id)
    return InboxResponse(
        items=[InboxItemSchema.of_entry(e) for e in inbox.entries],
        unread_count=inbox.unread_count,
    )


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    MarkAllNotificationsRead(repo).execute(principal.user_id, utcnow())


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: int, principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    MarkNotificationRead(repo).execute(principal.user_id, notification_id, utcnow())


@router.post("/{notification_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss(notification_id: int, principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    """画面上部から閉じる（既読にもなる）。"""
    DismissNotification(repo).execute(principal.user_id, notification_id, utcnow())


# --- 端末への通知（Web Push）の購読 -------------------------------------------


@router.get("/push", response_model=PushConfigResponse)
async def push_config(_principal: AppOrWebPrincipalDep, sender: PushSenderDep) -> PushConfigResponse:
    public_key = sender.public_key() if sender.enabled else None
    return PushConfigResponse(enabled=public_key is not None, public_key=public_key)


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    body: PushSubscribeRequest,
    principal: AppOrWebPrincipalDep,
    subscriptions: PushSubscriptionRepoDep,
    sender: PushSenderDep,
) -> None:
    SubscribeToPush(subscriptions, sender).execute(principal.user_id, body.endpoint, body.keys.p256dh, body.keys.auth)


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    body: PushEndpointRequest, principal: AppOrWebPrincipalDep, subscriptions: PushSubscriptionRepoDep
) -> None:
    UnsubscribeFromPush(subscriptions).execute(principal.user_id, body.endpoint)


@router.post("/push/status", response_model=PushStatusResponse)
async def push_status(
    body: PushEndpointRequest, principal: AppOrWebPrincipalDep, subscriptions: PushSubscriptionRepoDep
) -> PushStatusResponse:
    """この端末の購読が、いまの利用者のものとして登録されているか。

    同じブラウザで別の人がログインし直すと、ブラウザ側の購読は残っているのにサーバーでは
    前の人のものになっている。画面のスイッチはこの答えで出す。
    """
    return PushStatusResponse(subscribed=subscriptions.exists(principal.user_id, body.endpoint))


# --- 管理画面からの配信 -------------------------------------------------------


@admin_router.get("", response_model=list[SentNotificationResponse])
async def list_sent(_principal: SenderDep, repo: NotificationRepoDep) -> list[SentNotificationResponse]:
    return [SentNotificationResponse.of(s) for s in ListSentNotifications(repo).execute()]


@admin_router.get("/audiences", response_model=AudienceOptionsResponse)
async def audience_options(_principal: SenderDep, db: DbDep) -> AudienceOptionsResponse:
    """宛先に選べる相手。``user:manage`` を持たない送り手にも、名前だけは見せる。"""
    groups = db.scalars(select(UserGroup).order_by(UserGroup.name)).all()
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.username, User.id)).all()
    return AudienceOptionsResponse(
        groups=[AudienceGroupSchema(id=g.id, name=g.name, member_count=len(g.members)) for g in groups],
        users=[AudienceUserSchema(id=u.id, username=u.username, email=u.email) for u in users],
    )


@admin_router.post("", status_code=status.HTTP_201_CREATED, response_model=SendNotificationResponse)
async def send_notification(
    body: SendNotificationRequest,
    principal: SenderDep,
    send: SendAndDeliverPushDep,
    audit: AuditRecorderDep,
) -> SendNotificationResponse:
    result = send.execute(
        SendNotificationCommand(
            title=body.title,
            body=body.body,
            link_url=body.link_url,
            channels=tuple(body.channels),
            audience_kind=body.audience.kind,
            audience_target_id=body.audience.target_id,
            sender_user_id=principal.user_id,
        ),
        utcnow(),
    )
    audit.execute(
        AuditEventType.NOTIFICATION_SENT,
        target=AuditTarget.of(AuditTargetType.NOTIFICATION, result.notification.id),
        reason=_audit_reason(result),
    )
    return SendNotificationResponse(
        notification=NotificationSchema.of(result.notification),
        audience=AudienceSchema(kind=body.audience.kind, target_id=result.notification.audience_target_id),
        recipient_count=len(result.recipient_user_ids),
        push_scheduled=result.push_scheduled,
    )


def _audit_reason(result: SendResultDTO) -> str:
    """監査ログの ``reason``。宛先・チャネル・配った人数（本文は入れない）。"""
    audience = result.notification.audience_kind
    if result.notification.audience_target_id is not None:
        audience += f":{result.notification.audience_target_id}"
    channels = ",".join(result.notification.channels)
    return f"audience={audience} channels={channels} recipients={len(result.recipient_user_ids)}"[:_MAX_REASON_LENGTH]


__all__ = ["admin_router", "router"]
