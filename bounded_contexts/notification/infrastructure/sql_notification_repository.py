"""SQLAlchemy implementation of ``INotificationRepository``.

Notifications (``notifications``) are tenant content; only the tenant's admin console sends them
and reads sent records (ADR-0079 §1). A user's own inbox (what was delivered) belongs to the
user, so it can be handled even when built without a tenant.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.notification.domain.entities.notification import (
    InboxEntry,
    Notification,
    SentNotification,
)
from bounded_contexts.notification.domain.repositories.notification_repository import INotificationRepository
from bounded_contexts.notification.domain.value_objects.audience import Audience, AudienceKind
from bounded_contexts.notification.domain.value_objects.channel import NotificationChannel
from bounded_contexts.notification.domain.value_objects.content import NotificationContent
from bounded_contexts.notification.infrastructure.notification_models import (
    NotificationDeliveryModel,
    NotificationModel,
)
from shared.kernel.timestamps import to_naive_utc


def _to_entity(row: NotificationModel) -> Notification:
    channels = {
        NotificationChannel.BELL: row.in_bell,
        NotificationChannel.BANNER: row.in_banner,
        NotificationChannel.PUSH: row.by_push,
    }
    return Notification(
        id=row.id,
        content=NotificationContent(title=row.title, body=row.body, link_url=row.link_url),
        channels=frozenset(c for c, on in channels.items() if on),
        audience=Audience(AudienceKind(row.audience_kind), row.audience_target_id),
        sender_user_id=row.sender_user_id,
        sent_at=row.sent_at,
    )


class SqlNotificationRepository(INotificationRepository):
    def __init__(self, session: Session, tenant_id: int | None = None) -> None:
        """Omitting ``tenant_id`` allows handling only the user's own inbox (``inbox`` etc.)."""
        self._session = session
        self._tenant_id = tenant_id

    def _tenant(self) -> int:
        if self._tenant_id is None:
            raise RuntimeError("sending and the sent list need the tenant")
        return self._tenant_id

    def add(self, notification: Notification, recipient_user_ids: list[int]) -> Notification:
        row = NotificationModel(
            tenant_id=self._tenant(),
            title=notification.content.title,
            body=notification.content.body,
            link_url=notification.content.link_url,
            in_bell=NotificationChannel.BELL in notification.channels,
            in_banner=NotificationChannel.BANNER in notification.channels,
            by_push=NotificationChannel.PUSH in notification.channels,
            audience_kind=notification.audience.kind.value,
            audience_target_id=notification.audience.target_id,
            sender_user_id=notification.sender_user_id,
            sent_at=to_naive_utc(notification.sent_at),
        )
        self._session.add(row)
        self._session.flush()
        if recipient_user_ids:
            self._session.execute(
                sa.insert(NotificationDeliveryModel),
                [{"notification_id": row.id, "user_id": uid} for uid in sorted(set(recipient_user_ids))],
            )
        return _to_entity(row)

    def inbox(self, user_id: int, *, limit: int) -> list[InboxEntry]:
        rows = self._session.execute(
            sa.select(NotificationModel, NotificationDeliveryModel.read_at, NotificationDeliveryModel.dismissed_at)
            .join(NotificationDeliveryModel, NotificationDeliveryModel.notification_id == NotificationModel.id)
            .where(NotificationDeliveryModel.user_id == user_id)
            # Push-only notifications have no place in the inbox list (shown neither in the bell nor at the top).
            .where(sa.or_(NotificationModel.in_bell, NotificationModel.in_banner))
            .order_by(NotificationModel.sent_at.desc(), NotificationModel.id.desc())
            .limit(limit)
        ).all()
        return [
            InboxEntry(notification=_to_entity(n), read_at=read_at, dismissed_at=dismissed_at)
            for n, read_at, dismissed_at in rows
        ]

    def unread_count(self, user_id: int) -> int:
        count = self._session.scalar(
            sa.select(sa.func.count())
            .select_from(NotificationDeliveryModel)
            .join(NotificationModel, NotificationDeliveryModel.notification_id == NotificationModel.id)
            .where(NotificationDeliveryModel.user_id == user_id)
            .where(NotificationDeliveryModel.read_at.is_(None))
            .where(NotificationModel.in_bell)
        )
        return int(count or 0)

    def _delivery(self, user_id: int, notification_id: int) -> NotificationDeliveryModel | None:
        return self._session.get(NotificationDeliveryModel, (notification_id, user_id))

    def mark_read(self, user_id: int, notification_id: int, at: datetime) -> bool:
        delivery = self._delivery(user_id, notification_id)
        if delivery is None:
            return False
        if delivery.read_at is None:
            delivery.read_at = to_naive_utc(at)
        return True

    def mark_all_read(self, user_id: int, at: datetime) -> None:
        self._session.execute(
            sa.update(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.user_id == user_id)
            .where(NotificationDeliveryModel.read_at.is_(None))
            .values(read_at=to_naive_utc(at))
        )

    def dismiss(self, user_id: int, notification_id: int, at: datetime) -> bool:
        delivery = self._delivery(user_id, notification_id)
        if delivery is None:
            return False
        naive = to_naive_utc(at)
        if delivery.dismissed_at is None:
            delivery.dismissed_at = naive
        if delivery.read_at is None:
            delivery.read_at = naive
        return True

    def sent(self, *, limit: int) -> list[SentNotification]:
        # Counting is done in a subquery. ⚠ Selecting all columns with ``GROUP BY notifications.id``
        # is refused by MariaDB's ``ONLY_FULL_GROUP_BY`` (it ignores functional dependency on the primary key).
        counts = (
            sa.select(
                NotificationDeliveryModel.notification_id.label("notification_id"),
                sa.func.count().label("recipients"),
                sa.func.count(NotificationDeliveryModel.read_at).label("read"),
            )
            .group_by(NotificationDeliveryModel.notification_id)
            .subquery()
        )
        rows = self._session.execute(
            sa.select(
                NotificationModel,
                sa.func.coalesce(counts.c.recipients, 0),
                sa.func.coalesce(counts.c.read, 0),
            )
            .outerjoin(counts, counts.c.notification_id == NotificationModel.id)
            .where(NotificationModel.tenant_id == self._tenant())
            .order_by(NotificationModel.sent_at.desc(), NotificationModel.id.desc())
            .limit(limit)
        ).all()
        return [
            SentNotification(notification=_to_entity(n), recipient_count=int(r), read_count=int(rd))
            for n, r, rd in rows
        ]


__all__ = ["SqlNotificationRepository"]
