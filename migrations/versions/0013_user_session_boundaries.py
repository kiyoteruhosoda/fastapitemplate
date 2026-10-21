"""user session boundaries

``user_session_boundaries`` を足す（ADR-0057）。1 人 1 行で、その時刻より前に出した
トークンでは更新・出し直しをさせない。パスワードを変えたときに入る。

**表を足すだけ**で、既存の表には触れない。``users`` の列にしないのは、古い移行
（据え付けの ``0002``）が ``User`` のモデルで ``users`` を書くため（列を足すと、
この移行より前の段で「列が無い」で落ちる）。

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
