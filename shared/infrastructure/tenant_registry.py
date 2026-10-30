"""テナントの外側の台帳（ADR-0079 §1・§5）。システム管理者だけが使う。

テナントの**中身は読まない**。数えるのは人数だけで、消すときも表の宣言
（``shared/infrastructure/models/tenancy.py``）に従って機械的に消す。
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

#: 消すときも残す表（テナントを消しても「誰が何をしたか」は残す。ADR-0075 §1）
_KEPT_ON_REMOVAL = frozenset({"audit_log"})


def member_counts(session: Session) -> dict[int, tuple[int, int]]:
    """テナントごとの人数（全員・有効な人）。中身ではなく数だけ。"""
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
    """テナントを、人・中身・自作のロールごと消す（監査ログは残す）。

    消す順は表の依存の逆（指す側を先に）。テナントの表は ``tenant_id`` で、利用者に付く表は
    ``user_id`` で消す。宣言の無い表は試験が落とすので、ここで取りこぼすことは無い。
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
    """利用者を、その人に付く行（パスキー・招待・所属など）ごと消す。"""
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
    """テナントに属さない利用者（システム管理者）。"""
    return session.scalars(
        sa.select(User)
        .outerjoin(UserTenant, UserTenant.user_id == User.id)
        .where(UserTenant.user_id.is_(None))
        .order_by(User.id)
    ).all()


def count_active_system_administrators(session: Session) -> int:
    """テナントの登録・停止を担える有効な運用者の数（0 にしない）。サポート担当は数えない。"""
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
