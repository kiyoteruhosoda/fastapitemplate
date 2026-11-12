"""Tables of the notification context (ADR-0081 §3).

- ``notifications`` -- one row per sent notification
- ``notification_deliveries`` -- one row per recipient (members as of sending), with read/dismissed state
- ``web_push_subscriptions`` -- one subscription per device (browser)
- ``app_device_tokens`` -- FCM registration token per installed mobile app (ADR-0081 §5)

Channels are separate columns (``in_bell`` / ``in_banner`` / ``by_push``), so "unread count in
the bell" is a plain condition rather than a substring match.

⚠ **Don't put a unique constraint directly on ``endpoint``.** Push service URLs run to hundreds of
characters, beyond MariaDB's (utf8mb4) index length limit. Keep a sha256 in another column and make that unique.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base

# No DB-native ENUM (becomes VARCHAR with a CHECK constraint)
AUDIENCE_KIND = sa.Enum("all", "group", "user", name="notification_audience_kind", native_enum=False)


class NotificationModel(Base):
    __tablename__ = "notifications"
    __table_args__ = declared(Tenancy.TENANT)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    body: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    link_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    in_bell: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    in_banner: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    by_push: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    audience_kind: Mapped[str] = mapped_column(AUDIENCE_KIND, nullable=False)
    #: Group or user ID. ⚠ No foreign key (keeps "who it was sent to" even if the target is deleted).
    audience_target_id: Mapped[int | None] = mapped_column(BigIntPk, nullable=True)
    #: Admin who sent it. ⚠ No foreign key (like the audit log, the record survives deletion).
    sender_user_id: Mapped[int | None] = mapped_column(BigIntPk, nullable=True)
    sent_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, index=True)


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = declared(Tenancy.PERSONAL)

    notification_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    read_at = mapped_column(sa.DateTime(), nullable=True)
    dismissed_at = mapped_column(sa.DateTime(), nullable=True)


class WebPushSubscriptionModel(Base):
    __tablename__ = "web_push_subscriptions"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint_sha256: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    p256dh: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    auth: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class AppDeviceTokenModel(Base):
    """One installed mobile app (ADR-0081 §5). Tokens are long too, so uniqueness uses a sha256 column."""

    __tablename__ = "app_device_tokens"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_sha256: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    token: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    platform: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    #: Last time it was re-registered. The app re-registers on every launch, so a stale row
    #: hints at a device that is no longer used.
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = [
    "AUDIENCE_KIND",
    "AppDeviceTokenModel",
    "NotificationDeliveryModel",
    "NotificationModel",
    "WebPushSubscriptionModel",
]
