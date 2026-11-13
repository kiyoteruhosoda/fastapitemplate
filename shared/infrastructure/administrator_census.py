"""Count active users holding the "administration core" (ADR-0078 §4)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth.authority import ADMINISTRATION_CORE
from shared.infrastructure.models import Permission, User, UserTenant, role_permissions, user_roles


def count_active_administrators(session: Session, tenant_id: int | None) -> int:
    """Number of active users holding all of ``ADMINISTRATION_CORE`` (even across several roles).

    Counted **inside that tenant** (the "administration core" is per tenant; ADR-0079 §1 decision 7).
    If ``tenant_id`` is ``None``, counted among users outside the tenants.
    Call after ``flush``ing the change. If 0, nobody could redistribute permissions after that change.
    """
    in_tenant = UserTenant.tenant_id.is_(None) if tenant_id is None else UserTenant.tenant_id == tenant_id
    holders = (
        sa.select(user_roles.c.user_id)
        .join(User, User.id == user_roles.c.user_id)
        .outerjoin(UserTenant, UserTenant.user_id == User.id)
        .where(in_tenant)
        .join(role_permissions, role_permissions.c.role_id == user_roles.c.role_id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(User.is_active.is_(True), Permission.code.in_(ADMINISTRATION_CORE))
        .group_by(user_roles.c.user_id)
        .having(sa.func.count(sa.distinct(Permission.code)) == len(ADMINISTRATION_CORE))
        .subquery()
    )
    return session.scalar(sa.select(sa.func.count()).select_from(holders)) or 0


__all__ = ["count_active_administrators"]
