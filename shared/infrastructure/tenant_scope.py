"""テナントの中の利用者・グループへの入口（ADR-0061 決定 5）。

管理画面・お知らせの宛先・グループの所属候補は、どれも「自分のテナントの利用者・グループ」
しか扱わない。``select(User)`` をルーターで書くと絞り忘れても動いてしまうので、
引くのは必ずここを通す。別のテナントの行は「無い」（``None``）として返す
——呼び側は 404 にする（在ることも見せない）。

⚠ **``tenant_id`` に ``None`` を渡さない。** 「テナントに属さない主体」は中身を扱えない。
入口の依存関数（``presentation/fastapi/dependencies/tenant.py``）が先に 403 で断っている。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import Role, RoleTenant, Tenant, User, UserGroup, UserTenant


def tenant_admits(session: Session, user: User) -> bool:
    """この利用者のテナントが開いているか（止めたテナントの人は入れない）。

    テナントに属さない利用者（システム管理者）は、テナントの止め外しに左右されない。
    """
    if user.tenant_id is None:
        return True
    tenant = session.get(Tenant, user.tenant_id)
    return tenant is not None and tenant.is_active


@dataclass(frozen=True)
class TenantMembers:
    """1 つのテナントの利用者とグループ。"""

    session: Session
    tenant_id: int

    def users_query(self) -> sa.Select[tuple[User]]:
        """このテナントの利用者を引く問い合わせ（条件を足して使う）。"""
        return (
            sa.select(User)
            .join(UserTenant, UserTenant.user_id == User.id)
            .where(UserTenant.tenant_id == self.tenant_id)
        )

    def users(self, *, active_only: bool = False) -> Sequence[User]:
        query = self.users_query()
        if active_only:
            query = query.where(User.is_active.is_(True))
        return self.session.scalars(query.order_by(User.id)).all()

    def user(self, user_id: int) -> User | None:
        return self.session.scalar(self.users_query().where(User.id == user_id))

    def users_with_ids(self, user_ids: set[int]) -> Sequence[User]:
        if not user_ids:
            return []
        return self.session.scalars(self.users_query().where(User.id.in_(user_ids))).all()

    def admit(self, user: User) -> User:
        """新しい利用者をこのテナントへ入れる。"""
        user.join(self.tenant_id)
        return user

    def _groups(self) -> sa.Select[tuple[UserGroup]]:
        return sa.select(UserGroup).where(UserGroup.tenant_id == self.tenant_id)

    def groups(self) -> Sequence[UserGroup]:
        return self.session.scalars(self._groups().order_by(UserGroup.name)).all()

    def group(self, group_id: int) -> UserGroup | None:
        return self.session.scalar(self._groups().where(UserGroup.id == group_id))

    def group_named(self, name: str) -> UserGroup | None:
        return self.session.scalar(self._groups().where(UserGroup.name == name))

    def new_group(self, name: str, description: str) -> UserGroup:
        return UserGroup(tenant_id=self.tenant_id, name=name, description=description)

    def _roles(self) -> sa.Select[tuple[Role]]:
        """このテナントで使えるロール: 共有の雛形（システムのロールを除く）と、自分で作ったもの（ADR-0063）。"""
        shared = sa.and_(RoleTenant.tenant_id.is_(None), Role.name.not_in(list(master_data.SYSTEM_ROLES)))
        return (
            sa.select(Role)
            .outerjoin(RoleTenant, RoleTenant.role_id == Role.id)
            .where(sa.or_(shared, RoleTenant.tenant_id == self.tenant_id))
        )

    def roles(self) -> Sequence[Role]:
        return self.session.scalars(self._roles().order_by(Role.id)).all()

    def role(self, role_id: int) -> Role | None:
        """使えるロール（共有の雛形を含む）。中身を変えてよいかは :meth:`Role.tenant_id` で見る。"""
        return self.session.scalar(self._roles().where(Role.id == role_id))

    def roles_named(self, names: Sequence[str]) -> Sequence[Role]:
        if not names:
            return []
        return self.session.scalars(self._roles().where(Role.name.in_(list(names)))).all()

    def new_role(self, name: str) -> Role:
        role = Role(name=name)
        role.ownership = RoleTenant(tenant_id=self.tenant_id)
        return role


__all__ = ["TenantMembers", "tenant_admits"]
