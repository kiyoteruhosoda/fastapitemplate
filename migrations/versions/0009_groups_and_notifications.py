"""groups and notifications

Add the tables needed for groups (collections of users) and sending announcements (ADR-0081 §3),
and seed the permissions ``group:manage`` / ``notification:send``. The definitions live in
``shared/infrastructure/models/group.py`` and
``bounded_contexts/notification/infrastructure/notification_models.py``.
The permissions live in ``shared/domain/auth/master_data.py`` (not hard-coded here).

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
# No DB-native ENUM (becomes a VARCHAR with a CHECK constraint)
_AUDIENCE_KIND = sa.Enum("all", "group", "user", name="notification_audience_kind", native_enum=False)

_PERMISSION_CODES = ("group:manage", "notification:send")


def upgrade() -> None:
    # ⚠ Do not name the table groups (a reserved word in MySQL 8 / MariaDB).
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

    # No foreign keys on recipients/senders (keep "to whom / by whom" even if they are deleted).
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

    # ⚠ No unique constraint directly on endpoint (hundreds of characters; exceeds MariaDB's index length limit).
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

    # Permissions are seeded by re-running seed_master_data (idempotent; same as 0005).
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
