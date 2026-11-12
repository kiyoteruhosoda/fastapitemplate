"""rename admin role to owner

Rename the all-permissions role from ``admin`` to ``owner`` (ADR-0078 §5). The id and grants stay;
only the name column is rewritten. The values live in ``shared/domain/auth/master_data.py``.

Running only ``seed_master_data`` without renaming would see no ``owner``, **create another row**,
and leave ``admin`` with its grants. So rename first, then run it.

If ``owner`` already exists (a derived app created its own), nothing is rewritten. ``admin`` then
remains, so merge the grants by hand after checking them.

Does not seat the initial administrator (ADR-0078 §3).

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
