"""seed role templates

Add the per-family role templates (``system-admin`` / ``user-admin`` / ``auditor``)
(ADR-0078 §4). The values live in ``shared/domain/auth/master_data.py`` (not hard-coded here).

Just re-runs ``seed_master_data`` (idempotent). Does not seat the initial administrator (ADR-0078 §3).

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
