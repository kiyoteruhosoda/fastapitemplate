"""Management API outside tenants (``tenant:view`` to list, ``tenant:manage`` to change;
ADR-0079 §1, §5, ADR-0084 §3).

System administrators register, change, suspend and delete tenants and appoint the first tenant
administrator.

⚠ **Never touches tenant contents.** Only the tenant registry and member counts are returned, never
user lists or data. Appointing a tenant administrator only "creates a seat and invites"; the system
administrator never knows that person's password (they set it via the invitation email;
ADR-0079 §5).
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.system import (
    DesignationRequest,
    DesignationResponse,
    TenantCreatedResponse,
    TenantCreateRequest,
    TenantResponse,
    TenantUpdateRequest,
)
from presentation.fastapi.services.password_reset_service import PasswordResetService
from shared.domain.auth import master_data
from shared.infrastructure.models import Role, Tenant, TenantStatus, User
from shared.infrastructure.sign_in_directory import account_with_email
from shared.infrastructure.tenant_directory import tenant_issuing, tenant_named
from shared.infrastructure.tenant_registry import member_counts, remove_tenant
from shared.kernel.database.session import get_db
from shared.kernel.outbound_destination import DestinationRefusedError, check_https_url
from shared.kernel.settings.settings import settings

router = APIRouter(
    prefix="/api/system/tenants",
    tags=["system"],
    dependencies=[Depends(require_permission("tenant:view"))],
)

DbDep = Annotated[Session, Depends(get_db)]
#: Support staff may view the list. Register, change, appoint and delete are operators only
_MANAGES = [Depends(require_permission("tenant:manage"))]


def _to_response(tenant: Tenant, counts: dict[int, tuple[int, int]]) -> TenantResponse:
    total, active = counts.get(tenant.id, (0, 0))
    return TenantResponse(
        id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        issuer=tenant.issuer,
        client_id=tenant.client_id,
        status=tenant.status,
        member_count=total,
        active_member_count=active,
        created_at=tenant.created_at,
    )


def _tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "tenant_not_found"})
    return tenant


def _checked_issuer(raw: str | None) -> str | None:
    """Validate the shape of a tenant issuer (ADR-0090). Must be https, and on the same host as
    ``OIDC_ISSUER`` if that is set.

    The name is not resolved: at home assay's public name resolves to a private address, so
    resolving it would reject our own IdP.
    """
    issuer = (raw or "").rstrip("/")
    if not issuer:
        return None
    try:
        host = check_https_url(issuer).hostname
    except DestinationRefusedError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_issuer"}) from error
    home = urlsplit(settings.oidc_issuer).hostname
    if home and host != home:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_issuer"})
    return issuer


def _ensure_issuer_free(db: Session, issuer: str | None, *, except_id: int | None = None) -> None:
    """An issuer can be bound to only one tenant (so a token determines the tenant uniquely)."""
    if not issuer:
        return
    holder = tenant_issuing(db, issuer)
    if holder is not None and holder.id != except_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "issuer_already_registered"})


def _designate(db: Session, tenant: Tenant, person: DesignationRequest, audit: AuditRecorderDep) -> DesignationResponse:
    """Create a tenant administrator seat and send the person an invitation (ADR-0079 §5)."""
    if account_with_email(db, person.email, tenant.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"})
    owner = db.scalars(sa.select(Role).where(Role.name == master_data.DEFAULT_ADMIN_ROLE)).one()
    # ⚠ No password is set (ADR-0076 §6). The person sets one via the invitation or claims the seat
    # through the tenant's IdP
    user = User(email=person.email, username=person.username, password_hash=None, is_active=True)
    user.roles = [owner]
    user.join(tenant.id)
    db.add(user)
    db.flush()
    sent = PasswordResetService().invite(db, user, place=tenant.display_name)
    # The target is a user, so this record is also visible to that tenant's admins
    # (ADR-0079 §2 decision 5)
    audit.execute(
        AuditEventType.TENANT_ADMIN_DESIGNATED,
        target=AuditTarget.of(AuditTargetType.USER, user.id),
        reason=f"tenant={tenant.id} invitation_sent={str(sent).lower()}",
    )
    return DesignationResponse(user_id=user.id, invitation_sent=sent)


@router.get("", response_model=list[TenantResponse])
def list_tenants(db: DbDep) -> list[TenantResponse]:
    counts = member_counts(db)
    return [_to_response(t, counts) for t in db.scalars(sa.select(Tenant).order_by(Tenant.id))]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantCreatedResponse, dependencies=_MANAGES)
def create_tenant(body: TenantCreateRequest, db: DbDep, audit: AuditRecorderDep) -> TenantCreatedResponse:
    if tenant_named(db, body.slug) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "tenant_already_exists"})
    issuer = _checked_issuer(body.issuer)
    _ensure_issuer_free(db, issuer)
    tenant = Tenant(
        slug=body.slug,
        display_name=body.display_name.strip(),
        issuer=issuer,
        client_id=body.client_id or None,
    )
    db.add(tenant)
    db.flush()
    audit.execute(AuditEventType.TENANT_CREATED, target=AuditTarget.of(AuditTargetType.TENANT, tenant.id))
    designation = _designate(db, tenant, body.first_admin, audit)
    return TenantCreatedResponse(tenant=_to_response(tenant, member_counts(db)), designation=designation)


@router.put("/{tenant_id}", response_model=TenantResponse, dependencies=_MANAGES)
def update_tenant(tenant_id: int, body: TenantUpdateRequest, db: DbDep, audit: AuditRecorderDep) -> TenantResponse:
    """Change name, federation target and status (active / suspended). Members of a suspended
    tenant can no longer sign in."""
    tenant = _tenant(db, tenant_id)
    if body.issuer is not None:
        issuer = _checked_issuer(body.issuer)
        _ensure_issuer_free(db, issuer, except_id=tenant.id)
        tenant.issuer = issuer
    if body.client_id is not None:
        tenant.client_id = body.client_id or None
    if body.display_name is not None:
        tenant.display_name = body.display_name.strip()
    if body.status is not None:
        tenant.status = TenantStatus(body.status).value
    db.flush()
    changed = sorted(name for name, value in body.model_dump().items() if value is not None)
    audit.execute(
        AuditEventType.TENANT_UPDATED,
        target=AuditTarget.of(AuditTargetType.TENANT, tenant.id),
        reason=f"fields={','.join(changed) or 'none'}",
    )
    return _to_response(tenant, member_counts(db))


@router.post(
    "/{tenant_id}/administrators",
    status_code=status.HTTP_201_CREATED,
    response_model=DesignationResponse,
    dependencies=_MANAGES,
)
def designate_administrator(
    tenant_id: int, body: DesignationRequest, db: DbDep, audit: AuditRecorderDep
) -> DesignationResponse:
    """Appoint a tenant administrator (the first one, or a recovery when none remain).

    ⚠ **Existing users are never promoted to administrator** (staffing inside a tenant is the
    tenant administrator's job). This only creates a new seat and invites.
    """
    return _designate(db, _tenant(db, tenant_id), body, audit)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_MANAGES)
def delete_tenant(tenant_id: int, db: DbDep, audit: AuditRecorderDep) -> None:
    """Delete a tenant along with its people and data (audit logs are kept). **It must be
    suspended first.**

    The suspend step exists so a single misclick cannot wipe a family's or organization's data.
    """
    tenant = _tenant(db, tenant_id)
    if tenant.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "tenant_not_suspended"})
    remove_tenant(db, tenant)
    audit.execute(AuditEventType.TENANT_DELETED, target=AuditTarget.of(AuditTargetType.TENANT, tenant_id))


__all__ = ["router"]
