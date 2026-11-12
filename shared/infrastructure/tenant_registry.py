"""Registry outside the tenants (ADR-0079 §1, §5). Used only by system administrators.

**Never reads tenant content.** It only counts people, and deletion too is done mechanically
following the table declarations (``shared/infrastructure/models/tenancy.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import (
    Role,
    RoleTenant,
    Tenant,
    User,
    UserTenant,
    role_permissions,
    user_roles,
)
from shared.infrastructure.models.tenancy import TENANCY_KEY, Tenancy
from shared.kernel.database.db import Base

#: Tables kept on deletion (even when a tenant is deleted, "who did what" is kept; ADR-0075 §1)
_KEPT_ON_REMOVAL = frozenset({"audit_log"})


def member_counts(session: Session) -> dict[int, tuple[int, int]]:
    """Number of people per tenant (all, active). Only counts, not content."""
    rows = session.execute(
        sa.select(
            UserTenant.tenant_id,
            sa.func.count(),
            sa.func.count(sa.case((User.is_active.is_(True), 1))),
        )
        .join(User, User.id == UserTenant.user_id)
        .group_by(UserTenant.tenant_id)
    ).all()
    return {int(tenant_id): (int(total), int(active)) for tenant_id, total, active in rows}


def remove_tenant(session: Session, tenant: Tenant) -> None:
    """Delete a tenant together with its people, content and self-made roles (audit logs are kept).

    Deletion runs in reverse dependency order (referencing tables first). Tenant tables are deleted
    by ``tenant_id``, tables attached to users by ``user_id``. Tables without a declaration fail the
    tests, so nothing is missed here.
    """
    people = list(session.scalars(sa.select(UserTenant.user_id).where(UserTenant.tenant_id == tenant.id)))
    own_roles = list(session.scalars(sa.select(RoleTenant.role_id).where(RoleTenant.tenant_id == tenant.id)))
    for table in reversed(Base.metadata.sorted_tables):
        _clear(session, table, tenant.id, people)
    if own_roles:
        session.execute(role_permissions.delete().where(role_permissions.c.role_id.in_(own_roles)))
        session.execute(sa.delete(Role).where(Role.id.in_(own_roles)))
    if people:
        session.execute(sa.delete(User).where(User.id.in_(people)))
    session.delete(tenant)
    session.flush()


def remove_people(session: Session, people: Sequence[int]) -> None:
    """Delete users together with the rows attached to them (passkeys, invitations, membership, etc.)."""
    if not people:
        return
    for table in reversed(Base.metadata.sorted_tables):
        if table.info.get(TENANCY_KEY) == Tenancy.PERSONAL and "user_id" in table.columns:
            session.execute(table.delete().where(table.c.user_id.in_(people)))
    session.execute(sa.delete(User).where(User.id.in_(people)))
    session.flush()


def _clear(session: Session, table: sa.Table, tenant_id: int, people: Sequence[int]) -> None:
    kind = table.info.get(TENANCY_KEY)
    if table.name in _KEPT_ON_REMOVAL:
        return
    if kind == Tenancy.TENANT and "tenant_id" in table.columns:
        session.execute(table.delete().where(table.c.tenant_id == tenant_id))
    elif kind == Tenancy.PERSONAL and "user_id" in table.columns and people:
        session.execute(table.delete().where(table.c.user_id.in_(people)))


def system_administrators(session: Session) -> Sequence[User]:
    """Users outside the tenants (system administrators)."""
    return session.scalars(
        sa.select(User)
        .outerjoin(UserTenant, UserTenant.user_id == User.id)
        .where(UserTenant.user_id.is_(None))
        .order_by(User.id)
    ).all()


def count_active_system_administrators(session: Session) -> int:
    """Number of active operators able to register/suspend tenants (never 0). Support staff do not count."""
    holders = (
        sa.select(User.id)
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(Role, Role.id == user_roles.c.role_id)
        .outerjoin(UserTenant, UserTenant.user_id == User.id)
        .where(
            UserTenant.user_id.is_(None),
            User.is_active.is_(True),
            Role.name == master_data.SYSTEM_ADMIN_ROLE,
        )
        .distinct()
        .subquery()
    )
    return session.scalar(sa.select(sa.func.count()).select_from(holders)) or 0


__all__ = [
    "count_active_system_administrators",
    "member_counts",
    "remove_people",
    "remove_tenant",
    "system_administrators",
]
