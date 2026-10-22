"""「管理の要」を持つ有効な利用者を数える（ADR-0051）。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth.authority import ADMINISTRATION_CORE
from shared.infrastructure.models import Permission, User, UserTenant, role_permissions, user_roles


def count_active_administrators(session: Session, tenant_id: int | None) -> int:
    """``ADMINISTRATION_CORE`` を（複数のロールにまたがってでも）すべて持つ有効な利用者の数。

    数えるのは**そのテナントの中**（「管理の要」はテナントごと。ADR-0061 決定 7）。
    ``tenant_id`` が ``None`` なら、テナントに属さない利用者の中で数える。
    変更を ``flush`` した後に呼ぶ。0 なら、その変更で誰も権限を配り直せなくなる。
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
