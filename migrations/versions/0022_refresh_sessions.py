"""refresh sessions

ログインごとの控え ``refresh_sessions`` を足す（ADR-0091）。定義の正本は
``shared/infrastructure/models/user.py``。

⚠ 控えの無い発行済みのリフレッシュトークンは受け付けなくなるので、配った直後に全員が 1 回入り直す。

Revision ID: refresh_sessions
Revises: content_settings
Create Date: 2026-10-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "refresh_sessions"
down_revision = "content_settings"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("current_jti", sa.String(length=32), nullable=False),
        sa.Column("previous_jti", sa.String(length=32), nullable=True),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_expires_at", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
