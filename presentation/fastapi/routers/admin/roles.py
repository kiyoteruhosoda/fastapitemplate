"""Role management API (create, update and delete require ``role:manage``).

Only listing is also allowed with ``user:manage``, because the screen that assigns roles to users
needs to know which roles exist (ADR-0078 §2).

Granting permissions (scopes) to a role is effectively a permission change, so create, update and
delete are recorded in the audit log. On update, ``reason`` holds the **permission codes after the
grant** (so who granted what can be verified later; permission codes are not PII).

Operations that change a role's permissions get a gate in addition to the scope (ADR-0078 §4).
You cannot add or remove permissions you don't hold yourself, and a change that leaves zero people
with the "key admin" permissions is rejected.

Only **roles usable in your own tenant** can be handled (ADR-0079 §3). The templates
(``master_data.ROLES``) are shared by all tenants, so they appear in the list but cannot be
changed (403 ``shared_role``). A created role belongs to the tenant that created it and is
invisible to other tenants (404).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import require_any_permission, require_permission
from presentation.fastapi.routers.admin.authority_guard import Administration, AdministrationDep, permissions_of
from presentation.fastapi.schemas.admin import (
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)
from shared.domain.auth.authority import changed
from shared.infrastructure.models import Permission, Role
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/admin/roles", tags=["admin"])

# Changing roles requires role:manage. Reading is also allowed with user:manage (ADR-0078 §2).
_MANAGE_ROLES = Depends(require_permission("role:manage"))
_READ_ROLES = Depends(require_any_permission("role:manage", "user:manage"))

DbDep = Annotated[Session, Depends(get_db)]

# The reason column is 255 chars. Truncate when building it so roles with many permissions fit.
_MAX_REASON_LENGTH = 255


def _to_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        permissions=sorted(p.code for p in role.permissions),
        shared=role.tenant_id is None,
    )


def _resolve_permissions(db: Session, codes: list[str]) -> list[Permission]:
    permissions = db.scalars(select(Permission).where(Permission.code.in_(codes))).all()
    missing = set(codes) - {p.code for p in permissions}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_permissions", "permissions": sorted(missing)},
        )
    return list(permissions)


def _granted_scopes(role: Role) -> str:
    """The "permissions after the grant" put in the audit log ``reason``."""
    return f"scopes={','.join(sorted(p.code for p in role.permissions))}"[:_MAX_REASON_LENGTH]


@router.get("", response_model=list[RoleResponse], dependencies=[_READ_ROLES])
def list_roles(admin: AdministrationDep) -> list[RoleResponse]:
    return [_to_response(r) for r in admin.members.roles()]


def _own_role(admin: Administration, role_id: int) -> Role:
    """A role that may be modified. 404 if not visible, 403 if it is a shared template."""
    role = admin.members.role(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "role_not_found"})
    if role.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "shared_role"})
    return role


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleResponse,
    dependencies=[_MANAGE_ROLES],
)
def create_role(body: RoleCreateRequest, admin: AdministrationDep, audit: AuditRecorderDep) -> RoleResponse:
    db = admin.db
    if db.scalar(select(Role).where(Role.name == body.name)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "role_already_exists"},
        )
    permissions = _resolve_permissions(db, body.permissions)
    admin.ensure_within_authority(p.code for p in permissions)
    role = admin.members.new_role(body.name)
    role.permissions = permissions
    db.add(role)
    db.flush()
    audit.execute(
        AuditEventType.ROLE_CREATED,
        target=AuditTarget.of(AuditTargetType.ROLE, role.id),
        reason=_granted_scopes(role),
    )
    return _to_response(role)


@router.put("/{role_id}", response_model=RoleResponse, dependencies=[_MANAGE_ROLES])
def update_role(
    role_id: int,
    body: RoleUpdateRequest,
    admin: AdministrationDep,
    audit: AuditRecorderDep,
) -> RoleResponse:
    db = admin.db
    role = _own_role(admin, role_id)
    if body.name is not None:
        same_name = db.scalar(select(Role).where(Role.name == body.name, Role.id != role_id))
        if same_name is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "role_already_exists"},
            )
        role.name = body.name
    if body.permissions is not None:
        permissions = _resolve_permissions(db, body.permissions)
        admin.ensure_within_authority(changed(permissions_of([role]), (p.code for p in permissions)))
        role.permissions = permissions
    admin.ensure_an_administrator_remains()
    audit.execute(
        AuditEventType.ROLE_UPDATED,
        target=AuditTarget.of(AuditTargetType.ROLE, role_id),
        reason=_granted_scopes(role),
    )
    return _to_response(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_MANAGE_ROLES])
def delete_role(role_id: int, admin: AdministrationDep, audit: AuditRecorderDep) -> None:
    db = admin.db
    role = _own_role(admin, role_id)
    admin.ensure_within_authority(permissions_of([role]))
    role.permissions = []
    db.delete(role)
    admin.ensure_an_administrator_remains()
    audit.execute(
        AuditEventType.ROLE_DELETED,
        target=AuditTarget.of(AuditTargetType.ROLE, role_id),
    )
