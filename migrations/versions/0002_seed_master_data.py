"""seed master data

Seed roles, permissions and the initial administrator. The values live in
``shared/domain/auth/master_data.py`` (not hard-coded here).

Revision ID: seed_master_data
Revises: init_master
Create Date: 2026-07-17

"""

from __future__ import annotations

import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "seed_master_data"
down_revision = "init_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data

    session = Session(bind=op.get_bind())
    seed_master_data(session)
    # The initial administrator is seated **only this once, at setup** (ADR-0078 §3). Later
    # migrations that add permissions call only ``seed_master_data``.
    ensure_default_admin(session, password=os.environ.get("ADMIN_INITIAL_PASSWORD") or None)
    session.flush()


def downgrade() -> None:
    from shared.domain.auth import master_data
    from shared.infrastructure.models import (
        Permission,
        Role,
        User,
        role_permissions,
        user_roles,
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    bind.execute(role_permissions.delete())
    bind.execute(user_roles.delete())
    session.query(User).filter(User.email == master_data.DEFAULT_ADMIN_EMAIL).delete()
    session.query(Permission).filter(Permission.code.in_(master_data.PERMISSION_CODES)).delete(
        synchronize_session=False
    )
    session.query(Role).filter(Role.name.in_([name for _, name in master_data.ROLES])).delete(synchronize_session=False)
    session.flush()
