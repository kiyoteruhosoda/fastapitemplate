"""seed audit permission

Seed the permission to view audit logs (``audit:view``) and grant it to the ``admin`` role. The
values live in ``shared/domain/auth/master_data.py`` (not hard-coded here).

Seeding is done by re-running ``seed_master_data``. It is idempotent (existing rows are not
changed), so when a permission code is added to the master data, "running it again" like this is
enough to apply it to existing DBs.

Revision ID: seed_audit_permission
Revises: audit_log
Create Date: 2026-07-30

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "seed_audit_permission"
down_revision = "audit_log"
branch_labels = None
depends_on = None

_PERMISSION_CODE = "audit:view"


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import seed_master_data

    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()


def downgrade() -> None:
    from shared.infrastructure.models import Permission, role_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    permission = session.query(Permission).filter(Permission.code == _PERMISSION_CODE).one_or_none()
    if permission is not None:
        bind.execute(role_permissions.delete().where(role_permissions.c.permission_id == permission.id))
        session.delete(permission)
    session.flush()
