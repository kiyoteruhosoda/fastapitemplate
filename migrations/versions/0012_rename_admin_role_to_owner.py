"""rename admin role to owner

全権限のロールの名前を ``admin`` から ``owner`` へ変える（ADR-0052）。id と付与は
そのまま、名前の列だけを書き換える。値の正本は ``shared/domain/auth/master_data.py``。

名前を変えずに ``seed_master_data`` だけを流すと、``owner`` が無いと見て**別の行を
作り**、``admin`` は付与ごと残る。だから先に名前を変えてから流す。

``owner`` が既にある（派生アプリが自前で作っていた）ときは書き換えない。そのときは
``admin`` が残るので、付与を見て手で寄せる。

初期管理者は据えない（ADR-0024）。

Revision ID: rename_admin_role_to_owner
Revises: seed_role_templates
Create Date: 2026-10-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "rename_admin_role_to_owner"
down_revision = "seed_role_templates"
branch_labels = None
depends_on = None

_OLD = "admin"
_NEW = "owner"


def _rename(old: str, new: str) -> None:
    bind = op.get_bind()
    roles = sa.table("roles", sa.column("name", sa.String))
    if bind.execute(sa.select(roles.c.name).where(roles.c.name == new)).first() is not None:
        return
    bind.execute(roles.update().where(roles.c.name == old).values(name=new))


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import seed_master_data

    _rename(_OLD, _NEW)
    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()


def downgrade() -> None:
    _rename(_NEW, _OLD)
