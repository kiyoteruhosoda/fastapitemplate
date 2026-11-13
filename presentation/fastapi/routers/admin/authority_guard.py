"""Gate for admin API operations that move permissions (ADR-0078 §4).

The scope check (``require_permission``) only answers "may this screen be used". This answers
whether, on that screen, **this permission may be moved for this target**.

- You cannot grant or revoke permissions you don't hold
- You cannot touch users who hold more permissions than you
- You cannot change your own roles, suspend yourself or delete yourself
- A change that leaves zero active users with the "key admin" permissions is rejected

Takes an :class:`Administration` bundling the operator and the request's DB session (every gate
works from these two).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.dependencies.tenant import TENANT_REQUIRED
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.domain.auth.authority import beyond
from shared.infrastructure.administrator_census import count_active_administrators
from shared.infrastructure.models import Role, User
from shared.infrastructure.tenant_scope import TenantMembers
from shared.kernel.database.session import get_db


def permissions_of(roles: Iterable[Role]) -> frozenset[str]:
    """Union of the permissions held by a set of roles."""
    return frozenset(p.code for role in roles for p in role.permissions)


@dataclass(frozen=True)
class Administration:
    """Who (``actor``) is performing the admin operation, in which session (``db``)."""

    actor: AuthenticatedPrincipal
    db: Session

    @property
    def members(self) -> TenantMembers:
        """Users and groups of the operator's tenant (ADR-0079 §1). 403 for someone outside any
        tenant."""
        if self.actor.tenant_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TENANT_REQUIRED})
        return TenantMembers(self.db, self.actor.tenant_id)

    def ensure_within_authority(self, required: Iterable[str]) -> None:
        """403 unless the operator holds all of ``required``.

        The comparison uses the **currently effective permissions** (after narrowing by the
        active role; ADR-0078 §1). While operating with a weaker role, stronger permissions
        cannot be granted.
        """
        missing = beyond(self.actor.permissions, required)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "beyond_your_permissions", "permissions": sorted(missing)},
            )

    def ensure_not_yourself(self, user: User) -> None:
        """Your own roles, active state and existence cannot be changed from the admin console.

        This prevents accidentally locking yourself out and ensures permission changes always
        pass through another person.
        """
        if user.id == self.actor.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "cannot_change_yourself"},
            )

    def ensure_an_administrator_remains(self) -> None:
        """``flush`` the change and recount. 409 if zero active users hold the "key admin" permissions.

        Access tokens stay valid until they expire (ADR-0076 §5), so an old token of someone
        whose role was removed may get through the gates above. The final check uses the current
        DB state. The exception rolls back the request's session, so the change is not kept.
        """
        self.db.flush()
        if count_active_administrators(self.db, self.actor.tenant_id) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "last_administrator"},
            )


def get_administration(
    actor: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Administration:
    return Administration(actor=actor, db=db)


AdministrationDep = Annotated[Administration, Depends(get_administration)]

__all__ = ["Administration", "AdministrationDep", "get_administration", "permissions_of"]
