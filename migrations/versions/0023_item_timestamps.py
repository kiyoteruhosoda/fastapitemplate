"""item timestamps

Add ``created_at`` / ``updated_at`` to items (task #799). Existing rows get the migration time
(the real times are not preserved). The definition lives in ``bounded_contexts/example/infrastructure/item_model.py``.

Revision ID: item_timestamps
Revises: refresh_sessions
Create Date: 2026-10-31

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from shared.kernel.timestamps import utcnow

# revision identifiers, used by Alembic.
revision = "item_timestamps"
down_revision = "refresh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.get_bind().execute(sa.text("UPDATE items SET created_at = :now, updated_at = :now"), {"now": utcnow()})
    with op.batch_alter_table("items") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("created_at")
