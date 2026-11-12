"""Entry point to users and groups inside a tenant (ADR-0079 §1 decision 5).

The admin screen, announcement recipients and group membership candidates all handle only "users
and groups of one's own tenant". Writing ``select(User)`` in a router still works when the
filter is forgotten, so lookups must always go through here. Rows of another tenant are returned
as "absent" (``None``); the caller turns that into 404 (not even revealing that they exist).

⚠ **Never pass ``None`` as ``tenant_id``.** "A principal outside the tenants" cannot handle
content. The entry dependency (``presentation/fastapi/dependencies/tenant.py``) already refuses
with 403 first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import Role, RoleTenant, Tenant, User, UserGroup, UserTenant


def tenant_admits(session: Session, user: User) -> bool:
    """Whether this user's tenant is open (people of a suspended tenant cannot sign in).

    Users outside the tenants (system administrators) are unaffected by suspending tenants.
    """
    if user.tenant_id is None:
        return True
    tenant = session.get(Tenant, user.tenant_id)
    return tenant is not None and tenant.is_active


@dataclass(frozen=True)
class TenantMembers:
    """Users and groups of one tenant."""

    session: Session
    tenant_id: int

    def users_query(self) -> sa.Select[User]:
        """Query that selects this tenant's users (add conditions to use it)."""
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

    def user_with_email(self, email: str) -> User | None:
        return self.session.scalar(self.users_query().where(User.email == email))

    def users_with_ids(self, user_ids: set[int]) -> Sequence[User]:
        if not user_ids:
            return []
        return self.session.scalars(self.users_query().where(User.id.in_(user_ids))).all()

    def admit(self, user: User) -> User:
        """Put a new user into this tenant."""
        user.join(self.tenant_id)
        return user

    def _groups(self) -> sa.Select[UserGroup]:
        return sa.select(UserGroup).where(UserGroup.tenant_id == self.tenant_id)

    def groups(self) -> Sequence[UserGroup]:
        return self.session.scalars(self._groups().order_by(UserGroup.name)).all()

    def group(self, group_id: int) -> UserGroup | None:
        return self.session.scalar(self._groups().where(UserGroup.id == group_id))

    def group_named(self, name: str) -> UserGroup | None:
        return self.session.scalar(self._groups().where(UserGroup.name == name))

    def new_group(self, name: str, description: str) -> UserGroup:
        return UserGroup(tenant_id=self.tenant_id, name=name, description=description)

    def _roles(self) -> sa.Select[Role]:
        """Roles usable in this tenant: shared templates (excluding system roles) and those it
        created itself (ADR-0079 §3)."""
        shared = sa.and_(RoleTenant.tenant_id.is_(None), Role.name.not_in(list(master_data.SYSTEM_ROLES)))
        return (
            sa.select(Role)
            .outerjoin(RoleTenant, RoleTenant.role_id == Role.id)
            .where(sa.or_(shared, RoleTenant.tenant_id == self.tenant_id))
        )

    def roles(self) -> Sequence[Role]:
        return self.session.scalars(self._roles().order_by(Role.id)).all()

    def role(self, role_id: int) -> Role | None:
        """A usable role (shared templates included). Whether its content may be changed is
        checked via :meth:`Role.tenant_id`."""
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
