"""groups and notifications

グループ（利用者のまとまり）とお知らせの配信（ADR-0047）で要るテーブルを足し、
権限 ``group:manage`` / ``notification:send`` を投入する。定義の正本は
``shared/infrastructure/models/group.py`` と
``bounded_contexts/notification/infrastructure/notification_models.py``。
権限の正本は ``shared/domain/auth/master_data.py``（ここへ直書きしない）。

Revision ID: groups_and_notifications
Revises: password_is_optional
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "groups_and_notifications"
down_revision = "password_is_optional"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる）
_AUDIENCE_KIND = sa.Enum("all", "group", "user", name="notification_audience_kind", native_enum=False)

_PERMISSION_CODES = ("group:manage", "notification:send")


def upgrade() -> None:
    # ⚠ テーブル名を groups にしない（MySQL 8 / MariaDB の予約語）。
    op.create_table(
        "user_groups",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user_group_members",
        sa.Column("group_id", _BIGINT, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
        sa.ForeignKeyConstraint(["group_id"], ["user_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # 宛先・送り手には外部キーを張らない（相手を消しても「誰に・誰が送ったか」を残す）。
    op.create_table(
        "notifications",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_url", sa.String(length=1000), nullable=True),
        sa.Column("in_bell", sa.Boolean(), nullable=False),
        sa.Column("in_banner", sa.Boolean(), nullable=False),
        sa.Column("by_push", sa.Boolean(), nullable=False),
        sa.Column("audience_kind", _AUDIENCE_KIND, nullable=False),
        sa.Column("audience_target_id", _BIGINT, nullable=True),
        sa.Column("sender_user_id", _BIGINT, nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_sent_at", "notifications", ["sent_at"])

    op.create_table(
        "notification_deliveries",
        sa.Column("notification_id", _BIGINT, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])

    # ⚠ endpoint（数百文字）へ直接一意制約を張らない（MariaDB の索引長の上限を超える）。
    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("endpoint_sha256", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_sha256"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_web_push_subscriptions_user_id", "web_push_subscriptions", ["user_id"])

    # 権限の投入は seed_master_data の再実行で行う（冪等。0005 と同じ）。
    from shared.infrastructure.master_data_seeder import seed_master_data

    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()


def downgrade() -> None:
    from shared.infrastructure.models import Permission, role_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    for code in _PERMISSION_CODES:
        permission = session.query(Permission).filter(Permission.code == code).one_or_none()
        if permission is not None:
            bind.execute(role_permissions.delete().where(role_permissions.c.permission_id == permission.id))
            session.delete(permission)
    session.flush()

    op.drop_index("ix_web_push_subscriptions_user_id", table_name="web_push_subscriptions")
    op.drop_table("web_push_subscriptions")
    op.drop_index("ix_notification_deliveries_user_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_notifications_sent_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("user_group_members")
    op.drop_table("user_groups")
