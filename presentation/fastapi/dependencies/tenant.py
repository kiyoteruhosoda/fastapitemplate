"""主体のテナントを取り出す依存関数（ADR-0079 §1 決定 5）。

テナントの中身を扱う口は、リポジトリを組み立てるときにここからテナントを受け取る。
ルーター本文で ``tenant_id`` を書かない ——書き忘れても動いてしまい、気付くのは漏れた後になる。

⚠ **テナントに属さない主体（システム管理者）は 403。** 「全部のテナント」として扱わない。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import get_current_principal
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.tenant_scope import TenantMembers
from shared.kernel.database.session import get_db

TENANT_REQUIRED = "tenant_required"


async def get_current_tenant_id(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> int:
    if principal.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TENANT_REQUIRED})
    return principal.tenant_id


TenantIdDep = Annotated[int, Depends(get_current_tenant_id)]


def get_tenant_members(tenant_id: TenantIdDep, db: Annotated[Session, Depends(get_db)]) -> TenantMembers:
    return TenantMembers(session=db, tenant_id=tenant_id)


TenantMembersDep = Annotated[TenantMembers, Depends(get_tenant_members)]

__all__ = ["TENANT_REQUIRED", "TenantIdDep", "TenantMembersDep", "get_current_tenant_id", "get_tenant_members"]
