"""notes

共有メモ（``bounded_contexts/notes``。ADR-0078 §6 の見本）の表 ``notes`` を足し、権限
``note:view`` / ``note:write`` を投入する。定義の正本は
``bounded_contexts/notes/infrastructure/note_model.py``、権限の正本は
``shared/domain/auth/master_data.py``（ここへ直書きしない）。

初期管理者は据えない（ADR-0078 §3）。

Revision ID: notes
Revises: password_token_purpose
Create Date: 2026-10-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "notes"
down_revision = "password_token_purpose"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

_PERMISSION_CODES = ("note:view", "note:write")


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("tenant_id", _BIGINT, nullable=False),
        sa.Column("owner_user_id", _BIGINT, nullable=False),
        sa.Column("shared_group_id", _BIGINT, nullable=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_group_id"], ["user_groups.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notes_tenant_id", "notes", ["tenant_id"])
    op.create_index("ix_notes_owner_user_id", "notes", ["owner_user_id"])
    op.create_index("ix_notes_shared_group_id", "notes", ["shared_group_id"])

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

    op.drop_index("ix_notes_shared_group_id", table_name="notes")
    op.drop_index("ix_notes_owner_user_id", table_name="notes")
    op.drop_index("ix_notes_tenant_id", table_name="notes")
    op.drop_table("notes")
