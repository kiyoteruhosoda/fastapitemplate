"""sessions valid from

``users.sessions_valid_from`` を足す（ADR-0057）。この時刻より前に出したトークンでは
更新・出し直しをさせない。パスワードを変えたときに入る。

**列を足すだけ**で、既存の行は NULL（区切り無し＝今までどおり）になる。

Revision ID: sessions_valid_from
Revises: rename_admin_role_to_owner
Create Date: 2026-10-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "sessions_valid_from"
down_revision = "rename_admin_role_to_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("sessions_valid_from", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("sessions_valid_from")
