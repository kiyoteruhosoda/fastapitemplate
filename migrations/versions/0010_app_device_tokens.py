"""app device tokens

スマホアプリへの通知（FCM。ADR-0049）の宛先、``app_device_tokens`` を足す。定義の正本は
``bounded_contexts/notification/infrastructure/notification_models.py``。

Revision ID: app_device_tokens
Revises: groups_and_notifications
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "app_device_tokens"
down_revision = "groups_and_notifications"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    # ⚠ token（150〜200 文字、上限は決まっていない）へ直接一意制約を張らない。sha256 の列で取る。
    op.create_table(
        "app_device_tokens",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_app_device_tokens_user_id", "app_device_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_app_device_tokens_user_id", table_name="app_device_tokens")
    op.drop_table("app_device_tokens")
