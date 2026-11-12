"""Dependency that extracts the principal's tenant (ADR-0079 §1 decision 5).

Endpoints that handle tenant data get the tenant from here when building their repositories.
Don't write ``tenant_id`` in router bodies: forgetting it still works, and you only notice after a leak.

⚠ **A principal outside any tenant (system administrator) gets 403.** It is not treated as "all tenants".
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import get_operation_principal
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.tenant_scope import TenantMembers
from shared.kernel.database.session import get_db

TENANT_REQUIRED = "tenant_required"


async def get_current_tenant_id(
    # Machine principals pass too (this only extracts the tenant and grants nothing; the scope gate
    # decides access. ADR-0087)
    principal: AuthenticatedPrincipal = Depends(get_operation_principal),
) -> int:
    if principal.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TENANT_REQUIRED})
    return principal.tenant_id


TenantIdDep = Annotated[int, Depends(get_current_tenant_id)]


def get_tenant_members(tenant_id: TenantIdDep, db: Annotated[Session, Depends(get_db)]) -> TenantMembers:
    return TenantMembers(session=db, tenant_id=tenant_id)


TenantMembersDep = Annotated[TenantMembers, Depends(get_tenant_members)]

__all__ = ["TENANT_REQUIRED", "TenantIdDep", "TenantMembersDep", "get_current_tenant_id", "get_tenant_members"]
