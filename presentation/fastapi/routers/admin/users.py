"""User management API (requires ``user:manage``).

Create, update and delete are recorded in the audit log (``audit_log``). ``reason`` holds only
the **names of changed fields**, never the values themselves (email address, password)
(ADR-0075 §1).

The list also returns **"the ways this user can sign in"** (``entrances``) (ADR-0076 §7). With
two authentication systems, the number of open entrances is only visible side by side. The data
is **asked from each context**: password from the ``users`` column, TOTP and passkeys from
account_security, IdP links from identity_federation.

Assigning/removing roles, suspending and deleting get a gate in addition to the scope
(ADR-0078 §4). You cannot hand out permissions you don't hold, touch users stronger than you,
change yourself, or leave zero people with the "key admin" permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from bounded_contexts.account_security.application.use_cases.count_local_factors import (
    CountLocalFactors,
)
from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)
from bounded_contexts.account_security.infrastructure.sql_local_factor_directory import (
    SqlLocalFactorDirectory,
)
from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.application.use_cases.list_federated_issuers import (
    ListFederatedIssuers,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_issuer_directory import (
    SqlFederatedIssuerDirectory,
)
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.dependencies.tenant import TenantMembersDep
from presentation.fastapi.routers.admin.authority_guard import (
    Administration,
    AdministrationDep,
    permissions_of,
)
from presentation.fastapi.schemas.admin import (
    SignInEntrancesResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from shared.domain.auth.authority import changed
from shared.infrastructure.models import Role, User, user_group_members
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin"],
    dependencies=[Depends(require_permission("user:manage"))],
)

DbDep = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class _Inventory:
    """Inventory data. Fetched for everyone at once, not again per user."""

    factors: dict[int, LocalFactors]
    issuers: dict[int, tuple[str, ...]]

    @classmethod
    def of(cls, db: Session) -> _Inventory:
        return cls(
            factors=CountLocalFactors(SqlLocalFactorDirectory(db)).execute(),
            issuers=ListFederatedIssuers(SqlFederatedIssuerDirectory(db)).execute(),
        )

    @classmethod
    def none(cls) -> _Inventory:
        """A just-created user. No second factor or IdP link yet."""
        return cls(factors={}, issuers={})

    def entrances_of(self, user: User) -> SignInEntrancesResponse:
        factors = self.factors.get(user.id, LocalFactors())
        return SignInEntrancesResponse(
            password=user.has_local_password,
            totp=factors.totp,
            passkeys=factors.passkeys,
            identity_providers=list(self.issuers.get(user.id, ())),
        )


def _to_response(user: User, inventory: _Inventory) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        roles=sorted(r.name for r in user.roles),
        entrances=inventory.entrances_of(user),
    )


def _resolve_roles(admin: Administration, names: list[str]) -> list[Role]:
    """Fetch only roles usable in your own tenant (ADR-0079 §3). System roles cannot be used."""
    roles = admin.members.roles_named(names)
    missing = set(names) - {r.name for r in roles}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_roles", "roles": sorted(missing)},
        )
    return list(roles)


def _changed_fields(body: UserUpdateRequest) -> str:
    """The "what changed" put in the audit log ``reason``. Values themselves are not included."""
    fields = sorted(name for name, value in body.model_dump().items() if value is not None)
    return f"fields={','.join(fields)}" if fields else "fields=none"


@router.get("", response_model=list[UserResponse])
def list_users(db: DbDep, members: TenantMembersDep) -> list[UserResponse]:
    users = members.users()
    inventory = _Inventory.of(db)
    return [_to_response(u, inventory) for u in users]


def _authorize_update(admin: Administration, user: User, body: UserUpdateRequest) -> list[Role] | None:
    """Gate for updates (ADR-0078 §4). If it passes, return the new roles (``None`` if unchanged)."""
    # Rewriting the password of a stronger user would take over all of their permissions.
    if user.id != admin.actor.user_id:
        admin.ensure_within_authority(permissions_of(user.roles))
    if body.is_active is False:
        admin.ensure_not_yourself(user)
    if body.roles is None:
        return None
    new_roles = _resolve_roles(admin, body.roles)
    if {r.name for r in new_roles} != {r.name for r in user.roles}:
        admin.ensure_not_yourself(user)
    admin.ensure_within_authority(changed(permissions_of(user.roles), permissions_of(new_roles)))
    return new_roles


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def create_user(body: UserCreateRequest, admin: AdministrationDep, audit: AuditRecorderDep) -> UserResponse:
    db = admin.db
    # Email addresses are unique within a tenant (ADR-0079 §4)
    if admin.members.user_with_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "email_already_exists"},
        )
    user = User(
        email=body.email,
        username=body.username,
        password_hash=generate_password_hash(body.password),
        is_active=True,
    )
    roles = _resolve_roles(admin, body.roles)
    admin.ensure_within_authority(permissions_of(roles))
    user.roles = roles
    admin.members.admit(user)
    db.add(user)
    db.flush()
    audit.execute(
        AuditEventType.USER_CREATED,
        target=AuditTarget.of(AuditTargetType.USER, user.id),
    )
    return _to_response(user, _Inventory.none())


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    admin: AdministrationDep,
    audit: AuditRecorderDep,
) -> UserResponse:
    db = admin.db
    user = admin.members.user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    new_roles = _authorize_update(admin, user, body)
    if body.username is not None:
        user.username = body.username
    if body.is_active is not None:
        user.is_active = body.is_active
    if new_roles is not None:
        user.roles = new_roles
    if body.password is not None:
        user.password_hash = generate_password_hash(body.password)
        # When restoring a hijacked account, don't leave the hijacker's logins alive (ADR-0076 §8)
        user.end_sessions()
    admin.ensure_an_administrator_remains()
    audit.execute(
        AuditEventType.USER_UPDATED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
        reason=_changed_fields(body),
    )
    return _to_response(user, _Inventory.of(db))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: AdministrationDep, audit: AuditRecorderDep) -> None:
    db = admin.db
    user = admin.members.user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    admin.ensure_not_yourself(user)
    admin.ensure_within_authority(permissions_of(user.roles))
    user.roles = []
    # There is no relationship from User to groups, so remove memberships explicitly
    # (SQLite does not enforce foreign key CASCADE by default).
    db.execute(delete(user_group_members).where(user_group_members.c.user_id == user_id))
    db.delete(user)
    admin.ensure_an_administrator_remains()
    audit.execute(
        AuditEventType.USER_DELETED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
    )
