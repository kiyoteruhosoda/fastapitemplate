"""content settings

テナントごとのコンテンツ設定の表 ``content_settings`` を足す（ADR-0085）。定義の正本は
``bounded_contexts/content_settings/infrastructure/content_setting_model.py``。権限
（``content-settings:view`` / ``:write``）は ``0020_actors_and_roles`` で投入済み。

Revision ID: content_settings
Revises: actors_and_roles
Create Date: 2026-10-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "content_settings"
down_revision = "actors_and_roles"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "content_settings",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("tenant_id", _BIGINT, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "key", name="uq_content_settings_tenant_key"),
    )
    op.create_index("ix_content_settings_tenant_id", "content_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_content_settings_tenant_id", table_name="content_settings")
    op.drop_table("content_settings")
