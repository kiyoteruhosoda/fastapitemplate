"""ロール管理 API（作成・更新・削除は要 ``role:manage``）。

一覧の取得だけは ``user:manage`` でも通す。ユーザーへロールを割り当てる画面が
「どんなロールがあるか」を知る必要があるため（ADR-0078 §2）。

ロールへの権限（scope）付与は実質的な権限変更なので、作成・更新・削除を監査ログ
へ残す。更新時の ``reason`` には**付与後の権限コード**を入れる（誰が何の権限を
与えたかを後から検証できるようにするため。権限コードは PII ではない）。

権限の中身を変える操作には、scope とは別に関門を掛ける（ADR-0078 §4）。自分が
持っていない権限は足すことも外すこともできず、「管理の要」を持つ人を 0 人に
する変更は通さない。

扱えるのは**自分のテナントで使えるロールだけ**（ADR-0079 §3）。雛形（``master_data.ROLES``）は
全テナントが共有するので、一覧には出るが中身は変えられない（403 ``shared_role``）。
作ったロールは作ったテナントのもので、ほかのテナントからは見えない（404）。
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

# ロールを変える操作は role:manage。読むだけなら user:manage でも通す（ADR-0078 §2）。
_MANAGE_ROLES = Depends(require_permission("role:manage"))
_READ_ROLES = Depends(require_any_permission("role:manage", "user:manage"))

DbDep = Annotated[Session, Depends(get_db)]

# reason 列は 255 文字。権限を多く持つロールでも収まるよう組み立て時に切る。
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
    """監査ログの ``reason`` に載せる「付与後の権限」。"""
    return f"scopes={','.join(sorted(p.code for p in role.permissions))}"[:_MAX_REASON_LENGTH]


@router.get("", response_model=list[RoleResponse], dependencies=[_READ_ROLES])
async def list_roles(admin: AdministrationDep) -> list[RoleResponse]:
    return [_to_response(r) for r in admin.members.roles()]


def _own_role(admin: Administration, role_id: int) -> Role:
    """中身を変えてよいロール。見えなければ 404、共有の雛形なら 403。"""
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
async def create_role(body: RoleCreateRequest, admin: AdministrationDep, audit: AuditRecorderDep) -> RoleResponse:
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
async def update_role(
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
async def delete_role(role_id: int, admin: AdministrationDep, audit: AuditRecorderDep) -> None:
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
