"""actors and roles

権限とロールをアクターに合わせて組み直す（ADR-0084）。

- 改名（付与ごと引き継ぐ）: ``admin:system-settings`` → ``system-settings:write``、
  ``item:manage`` → ``item:write``
- 足す: ``system-settings:view`` / ``system:view`` / ``tenant:view`` / ``content-settings:view`` /
  ``content-settings:write`` と、ロール ``system-support`` / ``content-admin``（``seed_master_data``）
- 前にできたことは続けてできるようにする: 変えられた人には見るほうも付ける
  （``system-settings:write`` → ``:view``、``system:manage`` → ``system:view``、``tenant:manage`` → ``tenant:view``）
- 消す: ``permission:manage``（権限コードの一覧は ``role:manage`` で読む）

初期管理者は据えない（ADR-0078 §3）。

Revision ID: actors_and_roles
Revises: notes
Create Date: 2026-10-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "actors_and_roles"
down_revision = "notes"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

#: 前の名前 → 新しい名前
_RENAMED = (
    ("admin:system-settings", "system-settings:write"),
    ("item:manage", "item:write"),
)
#: 変えられる権限 → それを持つ人に付ける見る権限
_VIEW_OF = (
    ("system-settings:write", "system-settings:view"),
    ("system:manage", "system:view"),
    ("tenant:manage", "tenant:view"),
)
_DROPPED = "permission:manage"
#: この移行で足すもの（戻すときに消す）
_ADDED_PERMISSIONS = (
    "system-settings:view",
    "system:view",
    "tenant:view",
    "content-settings:view",
    "content-settings:write",
)
_ADDED_ROLES = ("system-support", "content-admin")

_roles = sa.table("roles", sa.column("id", _BIGINT), sa.column("name", sa.String))
_permissions = sa.table("permissions", sa.column("id", _BIGINT), sa.column("code", sa.String))
_role_permissions = sa.table("role_permissions", sa.column("role_id", _BIGINT), sa.column("permission_id", _BIGINT))
_user_roles = sa.table("user_roles", sa.column("user_id", _BIGINT), sa.column("role_id", _BIGINT))


def _permission_id(code: str) -> int | None:
    return op.get_bind().execute(sa.select(_permissions.c.id).where(_permissions.c.code == code)).scalar()


def _holders(permission_id: int) -> set[int]:
    rows = op.get_bind().execute(
        sa.select(_role_permissions.c.role_id).where(_role_permissions.c.permission_id == permission_id)
    )
    return set(rows.scalars())


def _rename(old: str, new: str) -> None:
    """``old`` を ``new`` に改名する。両方あれば ``old`` の付与を ``new`` へ移して ``old`` を消す。"""
    bind = op.get_bind()
    old_id = _permission_id(old)
    if old_id is None:
        return
    new_id = _permission_id(new)
    if new_id is None:
        bind.execute(_permissions.update().where(_permissions.c.id == old_id).values(code=new))
        return
    _grant(_holders(old_id) - _holders(new_id), new_id)
    _drop(old_id)


def _grant(role_ids: set[int], permission_id: int) -> None:
    if role_ids:
        op.get_bind().execute(
            _role_permissions.insert(), [{"role_id": rid, "permission_id": permission_id} for rid in sorted(role_ids)]
        )


def _drop(permission_id: int) -> None:
    bind = op.get_bind()
    bind.execute(_role_permissions.delete().where(_role_permissions.c.permission_id == permission_id))
    bind.execute(_permissions.delete().where(_permissions.c.id == permission_id))


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import seed_master_data

    for old, new in _RENAMED:
        _rename(old, new)

    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()

    for write, view in _VIEW_OF:
        write_id, view_id = _permission_id(write), _permission_id(view)
        if write_id is not None and view_id is not None:
            _grant(_holders(write_id) - _holders(view_id), view_id)

    dropped = _permission_id(_DROPPED)
    if dropped is not None:
        _drop(dropped)


def downgrade() -> None:
    bind = op.get_bind()
    for code in _ADDED_PERMISSIONS:
        permission_id = _permission_id(code)
        if permission_id is not None:
            _drop(permission_id)
    for name in _ADDED_ROLES:
        role_id = bind.execute(sa.select(_roles.c.id).where(_roles.c.name == name)).scalar()
        if role_id is not None:
            bind.execute(_user_roles.delete().where(_user_roles.c.role_id == role_id))
            bind.execute(_role_permissions.delete().where(_role_permissions.c.role_id == role_id))
            bind.execute(_roles.delete().where(_roles.c.id == role_id))
    for old, new in _RENAMED:
        _rename(new, old)

    # permission:manage は owner に返す（この移行の前の付与）
    if _permission_id(_DROPPED) is None:
        bind.execute(_permissions.insert().values(code=_DROPPED))
    owner = bind.execute(sa.select(_roles.c.id).where(_roles.c.name == "owner")).scalar()
    dropped = _permission_id(_DROPPED)
    if owner is not None and dropped is not None and owner not in _holders(dropped):
        _grant({owner}, dropped)
