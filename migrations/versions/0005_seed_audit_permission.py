"""seed audit permission

監査ログ閲覧の権限（``audit:view``）を投入し、``admin`` ロールへ付与する。値の
正本は ``shared/domain/auth/master_data.py``（ここへ直書きしない）。

投入は ``seed_master_data`` の再実行で行う。冪等（既存の行は変更しない）なので、
マスタデータへ権限コードを足したときはこのように「もう一度流す」だけで既存 DB へ
反映できる。

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
