"""Adding and removing people outside tenants (operators, support staff) (requires
``system:manage``; ADR-0079 §1, §5, ADR-0084 §4).

People outside tenants are users that belong to no tenant, with exactly one role from
``SYSTEM_ROLES`` (``system-admin`` for operators, ``system-support`` for support staff). Adding
one works like appointing a tenant administrator: create a seat and invite (the person sets
their own password).

- You cannot remove yourself (prevents lockout)
- A change that leaves zero active operators is rejected (nobody could manage tenants)
"""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.system import (
    DesignationResponse,
    SystemAdministratorResponse,
    SystemPersonRequest,
)
from presentation.fastapi.services.password_reset_service import PasswordResetService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.domain.auth import master_data
from shared.infrastructure.models import Role, User
from shared.infrastructure.sign_in_directory import account_with_email
from shared.infrastructure.tenant_registry import (
    count_active_system_administrators,
    remove_people,
    system_administrators,
)
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/system/administrators", tags=["system"])

DbDep = Annotated[Session, Depends(get_db)]
OperatorDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("system:manage"))]


def _to_response(user: User) -> SystemAdministratorResponse:
    role = next((r.name for r in user.roles if r.name in master_data.SYSTEM_ROLES), None)
    return SystemAdministratorResponse(
        id=user.id, email=user.email, username=user.username, is_active=user.is_active, role=role
    )


@router.get("", response_model=list[SystemAdministratorResponse])
def list_administrators(_operator: OperatorDep, db: DbDep) -> list[SystemAdministratorResponse]:
    return [_to_response(u) for u in system_administrators(db)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DesignationResponse)
def add_administrator(
    body: SystemPersonRequest, _operator: OperatorDep, db: DbDep, audit: AuditRecorderDep
) -> DesignationResponse:
    if account_with_email(db, body.email, None) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"})
    user = User(email=body.email, username=body.username, password_hash=None, is_active=True)
    user.roles = list(db.scalars(sa.select(Role).where(Role.name == body.role)))
    db.add(user)
    db.flush()
    sent = PasswordResetService().invite(db, user, place="system administrator")
    audit.execute(AuditEventType.SYSTEM_ADMIN_ADDED, target=AuditTarget.of(AuditTargetType.USER, user.id))
    return DesignationResponse(user_id=user.id, invitation_sent=sent)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_administrator(user_id: int, operator: OperatorDep, db: DbDep, audit: AuditRecorderDep) -> None:
    user = next((u for u in system_administrators(db) if u.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    if user.id == operator.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "cannot_change_yourself"})
    remove_people(db, [user.id])
    if count_active_system_administrators(db) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "last_administrator"})
    audit.execute(AuditEventType.SYSTEM_ADMIN_REMOVED, target=AuditTarget.of(AuditTargetType.USER, user_id))


__all__ = ["router"]
