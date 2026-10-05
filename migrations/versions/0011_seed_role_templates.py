"""seed role templates

系統ごとのロールの雛形（``system-admin`` / ``user-admin`` / ``auditor``）を足す
（ADR-0051）。値の正本は ``shared/domain/auth/master_data.py``（ここへ直書きしない）。

``seed_master_data`` を流し直すだけ（冪等）。初期管理者は据えない（ADR-0024）。

Revision ID: seed_role_templates
Revises: app_device_tokens
Create Date: 2026-10-05

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "seed_role_templates"
down_revision = "app_device_tokens"
branch_labels = None
depends_on = None

_ROLE_NAMES = ("system-admin", "user-admin", "auditor")


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import seed_master_data

    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()


def downgrade() -> None:
    from shared.infrastructure.models import Role, user_roles

    bind = op.get_bind()
    session = Session(bind=bind)
    for role in session.query(Role).filter(Role.name.in_(_ROLE_NAMES)).all():
        bind.execute(user_roles.delete().where(user_roles.c.role_id == role.id))
        role.permissions = []
        session.delete(role)
    session.flush()
