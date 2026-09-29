"""notification コンテキストのテーブル（ADR-0047）。

- ``notifications`` —— 送ったお知らせ 1 通 1 行
- ``notification_deliveries`` —— 宛先の 1 人ずつ（送った時点の顔ぶれ）。既読・閉じたかを持つ
- ``web_push_subscriptions`` —— 端末（ブラウザ）1 つの購読

チャネルは列を分けて持つ（``in_bell`` / ``in_banner`` / ``by_push``）。「ベルに出る未読の数」を
文字列の部分一致ではなく素直な条件で数えるため。

⚠ **``endpoint`` に一意制約を直接張らない。** 通知サービスの URL は数百文字あり、
MariaDB（utf8mb4）の索引の長さの上限を超える。sha256 を別の列に持って、そちらを一意にする。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base

# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる）
AUDIENCE_KIND = sa.Enum("all", "group", "user", name="notification_audience_kind", native_enum=False)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    body: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    link_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    in_bell: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    in_banner: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    by_push: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    audience_kind: Mapped[str] = mapped_column(AUDIENCE_KIND, nullable=False)
    #: グループ・利用者の ID。⚠ 外部キーを張らない（相手を消しても「誰に送ったか」を残す）。
    audience_target_id: Mapped[int | None] = mapped_column(BigIntPk, nullable=True)
    #: 送った管理者。⚠ 外部キーを張らない（監査ログと同じく、消しても記録を残す）。
    sender_user_id: Mapped[int | None] = mapped_column(BigIntPk, nullable=True)
    sent_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, index=True)


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"

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

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint_sha256: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    p256dh: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    auth: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


__all__ = ["AUDIENCE_KIND", "NotificationDeliveryModel", "NotificationModel", "WebPushSubscriptionModel"]
