"""content settings

Add the per-tenant content settings table ``content_settings`` (ADR-0085). The definition lives in
``bounded_contexts/content_settings/infrastructure/content_setting_model.py``. The permissions
(``content-settings:view`` / ``:write``) were already seeded by ``0020_actors_and_roles``.

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
