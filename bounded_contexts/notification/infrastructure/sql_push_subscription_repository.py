"""``IPushSubscriptionRepository`` の SQLAlchemy 実装。"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription
from bounded_contexts.notification.domain.repositories.push_subscription_repository import (
    IPushSubscriptionRepository,
)
from bounded_contexts.notification.infrastructure.notification_models import WebPushSubscriptionModel


def _digest(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


class SqlPushSubscriptionRepository(IPushSubscriptionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _find(self, endpoint: str) -> WebPushSubscriptionModel | None:
        return self._session.scalar(
            sa.select(WebPushSubscriptionModel).where(WebPushSubscriptionModel.endpoint_sha256 == _digest(endpoint))
        )

    def save(self, subscription: PushSubscription) -> None:
        row = self._find(subscription.endpoint)
        if row is None:
            row = WebPushSubscriptionModel(
                endpoint_sha256=_digest(subscription.endpoint), endpoint=subscription.endpoint
            )
            self._session.add(row)
        row.user_id = subscription.user_id
        row.p256dh = subscription.p256dh
        row.auth = subscription.auth
        self._session.flush()

    def remove(self, user_id: int, endpoint: str) -> None:
        self._session.execute(
            sa.delete(WebPushSubscriptionModel)
            .where(WebPushSubscriptionModel.endpoint_sha256 == _digest(endpoint))
            .where(WebPushSubscriptionModel.user_id == user_id)
        )

    def remove_endpoint(self, endpoint: str) -> None:
        self._session.execute(
            sa.delete(WebPushSubscriptionModel).where(WebPushSubscriptionModel.endpoint_sha256 == _digest(endpoint))
        )

    def for_users(self, user_ids: list[int]) -> list[PushSubscription]:
        if not user_ids:
            return []
        rows = self._session.scalars(
            sa.select(WebPushSubscriptionModel)
            .where(WebPushSubscriptionModel.user_id.in_(user_ids))
            .order_by(WebPushSubscriptionModel.id)
        ).all()
        return [PushSubscription(user_id=r.user_id, endpoint=r.endpoint, p256dh=r.p256dh, auth=r.auth) for r in rows]

    def exists(self, user_id: int, endpoint: str) -> bool:
        row = self._find(endpoint)
        return row is not None and row.user_id == user_id


__all__ = ["SqlPushSubscriptionRepository"]
