"""split system authority

Move global permissions from inside the tenants to outside (ADR-0079 §1 decision 4, ADR-0079 §3).

- Add ``role_tenants``. Existing self-made roles (not template names) go to the default tenant
- Add the permission ``tenant:manage`` and give it to ``system-admin`` (``seed_master_data``)
- Remove the global permissions (``admin:system-settings`` / ``system:manage`` / ``log:view`` /
  ``tenant:manage``) from every role other than ``system-admin`` (``owner``, ``manager``,
  ``auditor`` and self-made roles alike)
- Reseat holders of ``system-admin`` who are inside a tenant (no combining):
  people with only ``system-admin`` leave the tenant and become system administrators; people
  who also hold other roles lose ``system-admin``

Does not seat the initial administrator (ADR-0078 §3). Models are used only inside ``seed_master_data``.

Revision ID: split_system_authority
Revises: tenants
Create Date: 2026-10-22

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "split_system_authority"
down_revision = "tenants"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_SYSTEM_ROLE = "system-admin"
_SYSTEM_PERMISSIONS = ("admin:system-settings", "system:manage", "log:view", "tenant:manage")
#: Template names at the time of this migration. Any other role was created by a tenant.
_TEMPLATE_ROLES = ("owner", "manager", "member", "guest", "system-admin", "user-admin", "auditor", "admin")
#: Roles that get the global permissions back on downgrade (the grants before this migration)
_HELD_BEFORE = {
    "owner": _SYSTEM_PERMISSIONS[:3],
    "manager": ("log:view",),
    "auditor": ("log:view",),
}

_roles = sa.table("roles", sa.column("id", _BIGINT), sa.column("name", sa.String))
_permissions = sa.table("permissions", sa.column("id", _BIGINT), sa.column("code", sa.String))
_role_permissions = sa.table("role_permissions", sa.column("role_id", _BIGINT), sa.column("permission_id", _BIGINT))
_user_roles = sa.table("user_roles", sa.column("user_id", _BIGINT), sa.column("role_id", _BIGINT))
_user_tenants = sa.table("user_tenants", sa.column("user_id", _BIGINT), sa.column("tenant_id", _BIGINT))
_role_tenants = sa.table("role_tenants", sa.column("role_id", _BIGINT), sa.column("tenant_id", _BIGINT))


def _create_role_tenants() -> None:
    op.create_table(
        "role_tenants",
        sa.Column("role_id", _BIGINT, nullable=False),
        sa.Column("tenant_id", _BIGINT, nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("role_id"),
    )
    op.create_index("ix_role_tenants_tenant_id", "role_tenants", ["tenant_id"])


def _hand_custom_roles_to_the_default_tenant() -> None:
    bind = op.get_bind()
    tenant_id = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'default'")).scalar()
    if tenant_id is None:
        return
    custom = bind.execute(sa.select(_roles.c.id).where(_roles.c.name.not_in(_TEMPLATE_ROLES))).scalars().all()
    if custom:
        bind.execute(_role_tenants.insert(), [{"role_id": rid, "tenant_id": tenant_id} for rid in custom])


def _system_role_id() -> int | None:
    return op.get_bind().execute(sa.select(_roles.c.id).where(_roles.c.name == _SYSTEM_ROLE)).scalar()


def _strip_system_permissions(system_role: int | None) -> None:
    system_codes = sa.select(_permissions.c.id).where(_permissions.c.code.in_(_SYSTEM_PERMISSIONS))
    condition: sa.ColumnElement[bool] = _role_permissions.c.permission_id.in_(system_codes)
    if system_role is not None:
        condition = sa.and_(condition, _role_permissions.c.role_id != system_role)
    op.get_bind().execute(_role_permissions.delete().where(condition))


def _reseat_system_admins(system_role: int) -> None:
    """Seat system-admin holders who are inside a tenant on one side only (no combining)."""
    bind = op.get_bind()
    holders = (
        bind.execute(
            sa.select(_user_roles.c.user_id)
            .join(_user_tenants, _user_tenants.c.user_id == _user_roles.c.user_id)
            .where(_user_roles.c.role_id == system_role)
        )
        .scalars()
        .all()
    )
    for user_id in holders:
        others = bind.execute(
            sa.select(sa.func.count())
            .select_from(_user_roles)
            .where(_user_roles.c.user_id == user_id, _user_roles.c.role_id != system_role)
        ).scalar()
        if others:
            bind.execute(
                _user_roles.delete().where(_user_roles.c.user_id == user_id, _user_roles.c.role_id == system_role)
            )
        else:
            bind.execute(_user_tenants.delete().where(_user_tenants.c.user_id == user_id))


def upgrade() -> None:
    from shared.infrastructure.master_data_seeder import seed_master_data

    _create_role_tenants()
    _hand_custom_roles_to_the_default_tenant()
    session = Session(bind=op.get_bind())
    seed_master_data(session)
    session.flush()
    system_role = _system_role_id()
    _strip_system_permissions(system_role)
    if system_role is not None:
        _reseat_system_admins(system_role)


def downgrade() -> None:
    bind = op.get_bind()
    for role_name, codes in _HELD_BEFORE.items():
        role_id = bind.execute(sa.select(_roles.c.id).where(_roles.c.name == role_name)).scalar()
        if role_id is None:
            continue
        for code in codes:
            permission_id = bind.execute(sa.select(_permissions.c.id).where(_permissions.c.code == code)).scalar()
            if permission_id is not None:
                bind.execute(_role_permissions.insert().values(role_id=role_id, permission_id=permission_id))
    op.drop_index("ix_role_tenants_tenant_id", table_name="role_tenants")
    op.drop_table("role_tenants")
