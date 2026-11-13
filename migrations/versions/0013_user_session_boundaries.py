"""user session boundaries

Add ``user_session_boundaries`` (ADR-0076 §8). One row per user; tokens issued before that time
cannot refresh or be reissued. Set when the password changes.

**Only adds a table**; existing tables are untouched. It is not a ``users`` column because an old
migration (the setup ``0002``) writes ``users`` through the ``User`` model (adding a column would
make a step before this migration fail with "no such column").

Revision ID: user_session_boundaries
Revises: rename_admin_role_to_owner
Create Date: 2026-10-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "user_session_boundaries"
down_revision = "rename_admin_role_to_owner"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "user_session_boundaries",
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_session_boundaries")
