"""Notification API (ADR-0081 §3).

- ``/api/notifications`` -- the user's own inbox (bell, top of screen) and device push subscriptions.
  **Apps may call it too** (:data:`AppOrWebPrincipalDep`; ADR-0081 §1), so the mobile app can
  show the bell and top-of-screen notices through the same endpoints. No scope required (users only see their own)
- ``/api/admin/notifications`` -- sending and history from the admin console (``notification:send``)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

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
    RegisterDevice,
    SubscribeToPush,
    UnregisterDevice,
    UnsubscribeFromPush,
)
from bounded_contexts.notification.application.use_cases.send_notification import SendNotificationCommand
from bounded_contexts.notification.presentation.dependencies import (
    DevicePushSenderDep,
    DeviceTokenRepoDep,
    NotificationRepoDep,
    PushChannelsDep,
    PushSenderDep,
    PushSubscriptionRepoDep,
    SendAndDeliverPushDep,
    SentNotificationRepoDep,
)
from bounded_contexts.notification.presentation.schemas import (
    AudienceGroupResponse,
    AudienceOptionsResponse,
    AudienceResponse,
    AudienceUserResponse,
    DeviceRegisterRequest,
    DeviceUnregisterRequest,
    InboxItemResponse,
    InboxResponse,
    NotificationResponse,
    PushConfigResponse,
    PushEndpointRequest,
    PushStatusResponse,
    PushSubscribeRequest,
    SendNotificationRequest,
    SendNotificationResponse,
    SentNotificationResponse,
)
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.dependencies.tenant import TenantMembersDep
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.timestamps import utcnow

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
admin_router = APIRouter(prefix="/api/admin/notifications", tags=["admin"])

SenderDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("notification:send"))]

# The reason column is 255 characters.
_MAX_REASON_LENGTH = 255


# --- The user's own inbox --------------------------------------------------------


@router.get("", response_model=InboxResponse)
def list_my_notifications(principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> InboxResponse:
    """What to show in the bell and top of screen (newest first). The UI decides where via ``channels``."""
    inbox = ListInbox(repo).execute(principal.user_id)
    return InboxResponse(
        items=[InboxItemResponse.of_entry(e) for e in inbox.entries],
        unread_count=inbox.unread_count,
    )


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    MarkAllNotificationsRead(repo).execute(principal.user_id, utcnow())


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: int, principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    MarkNotificationRead(repo).execute(principal.user_id, notification_id, utcnow())


@router.post("/{notification_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss(notification_id: int, principal: AppOrWebPrincipalDep, repo: NotificationRepoDep) -> None:
    """Dismiss from the top of the screen (also marks as read)."""
    DismissNotification(repo).execute(principal.user_id, notification_id, utcnow())


# --- Device notification (Web Push) subscriptions ------------------------------


@router.get("/push", response_model=PushConfigResponse)
def push_config(_principal: AppOrWebPrincipalDep, channels: PushChannelsDep) -> PushConfigResponse:
    public_key = channels.web.public_key() if channels.web.enabled else None
    return PushConfigResponse(
        enabled=public_key is not None, public_key=public_key, device_enabled=channels.device.enabled
    )


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    body: PushSubscribeRequest,
    principal: AppOrWebPrincipalDep,
    subscriptions: PushSubscriptionRepoDep,
    sender: PushSenderDep,
) -> None:
    SubscribeToPush(subscriptions, sender).execute(principal.user_id, body.endpoint, body.keys.p256dh, body.keys.auth)


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    body: PushEndpointRequest, principal: AppOrWebPrincipalDep, subscriptions: PushSubscriptionRepoDep
) -> None:
    UnsubscribeFromPush(subscriptions).execute(principal.user_id, body.endpoint)


@router.post("/push/status", response_model=PushStatusResponse)
def push_status(
    body: PushEndpointRequest, principal: AppOrWebPrincipalDep, subscriptions: PushSubscriptionRepoDep
) -> PushStatusResponse:
    """Whether this device's subscription is registered to the current user.

    When someone else signs in again in the same browser, the browser still holds the subscription
    but the server has it as the previous user's. The UI's toggle is driven by this answer.
    """
    return PushStatusResponse(subscribed=subscriptions.exists(principal.user_id, body.endpoint))


# --- Mobile app notification (FCM) registration (ADR-0081 §5) -------------------------


@router.post("/device/register", status_code=status.HTTP_204_NO_CONTENT)
def register_device(
    body: DeviceRegisterRequest,
    principal: AppOrWebPrincipalDep,
    devices: DeviceTokenRepoDep,
    sender: DevicePushSenderDep,
) -> None:
    """Called by the app on every launch and sign-in (FCM may change the token)."""
    RegisterDevice(devices, sender).execute(principal.user_id, body.token, body.platform)


@router.post("/device/unregister", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    body: DeviceUnregisterRequest, principal: AppOrWebPrincipalDep, devices: DeviceTokenRepoDep
) -> None:
    """Called on sign-out (so the device stops receiving the previous user's notifications)."""
    UnregisterDevice(devices).execute(principal.user_id, body.token)


# --- Sending from the admin console --------------------------------------------


@admin_router.get("", response_model=list[SentNotificationResponse])
def list_sent(_principal: SenderDep, repo: SentNotificationRepoDep) -> list[SentNotificationResponse]:
    return [SentNotificationResponse.of(s) for s in ListSentNotifications(repo).execute()]


@admin_router.get("/audiences", response_model=AudienceOptionsResponse)
def audience_options(principal: SenderDep, members: TenantMembersDep) -> AudienceOptionsResponse:
    """Possible audience targets (within the sender's tenant only). Senders without ``user:manage`` still see names."""
    groups = members.groups()
    users = sorted(members.users(active_only=True), key=lambda u: (u.username, u.id))
    with_email = principal.can("user:manage")
    return AudienceOptionsResponse(
        groups=[AudienceGroupResponse(id=g.id, name=g.name, member_count=len(g.members)) for g in groups],
        users=[
            AudienceUserResponse(id=u.id, username=u.username, email=u.email if with_email else None) for u in users
        ],
    )


@admin_router.post("", status_code=status.HTTP_201_CREATED, response_model=SendNotificationResponse)
def send_notification(
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
        notification=NotificationResponse.of(result.notification),
        audience=AudienceResponse(kind=body.audience.kind, target_id=result.notification.audience_target_id),
        recipient_count=len(result.recipient_user_ids),
        push_scheduled=result.push_scheduled,
    )


def _audit_reason(result: SendResultDTO) -> str:
    """Audit log ``reason``: audience, channels and number delivered (not the body)."""
    audience = result.notification.audience_kind
    if result.notification.audience_target_id is not None:
        audience += f":{result.notification.audience_target_id}"
    channels = ",".join(result.notification.channels)
    return f"audience={audience} channels={channels} recipients={len(result.recipient_user_ids)}"[:_MAX_REASON_LENGTH]


__all__ = ["admin_router", "router"]
