"""グループ管理 API（ADR-0081 §3）。作成・更新・削除は要 ``group:manage``。

グループは「誰と誰か」を束ねるだけで権限を持たない（権限はロール）。一覧の取得は
``notification:send`` でも通す ——お知らせの宛先にグループを選ぶ人が、どんな
グループがあるかを知る必要があるため（ロールの一覧と同じ考え方。ADR-0078 §2）。

所属の候補（有効な利用者の一覧）は ``/users`` で返す。``user:manage`` を持たない
グループの管理者にも、名前とメールアドレスだけは見せる。``notification:send`` だけの
人には名前までで、メールアドレスは見せない（nolumiatask #785）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import get_current_principal, require_any_permission, require_permission
from presentation.fastapi.dependencies.tenant import TenantMembersDep
from presentation.fastapi.schemas.admin import (
    GroupCreateRequest,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdateRequest,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User, UserGroup
from shared.infrastructure.tenant_scope import TenantMembers

router = APIRouter(prefix="/api/admin/groups", tags=["admin"])

_MANAGE_GROUPS = Depends(require_permission("group:manage"))
_READ_GROUPS = Depends(require_any_permission("group:manage", "notification:send"))


def _member(user: User, *, with_email: bool = True) -> GroupMemberResponse:
    return GroupMemberResponse(id=user.id, username=user.username, email=user.email if with_email else None)


def _to_response(group: UserGroup, *, with_email: bool = True) -> GroupResponse:
    members = sorted(group.members, key=lambda u: (u.username, u.id))
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        members=[_member(u, with_email=with_email) for u in members],
    )


def _resolve_members(members: TenantMembers, member_ids: list[int]) -> list[User]:
    wanted = set(member_ids)
    users = members.users_with_ids(wanted)
    missing = wanted - {u.id for u in users}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_users", "users": sorted(missing)},
        )
    return list(users)


def _ensure_unique_name(members: TenantMembers, name: str, *, except_id: int | None = None) -> None:
    existing = members.group_named(name)
    if existing is not None and existing.id != except_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "group_already_exists"})


def _member_count(group: UserGroup) -> str:
    """監査ログの ``reason``。誰が入ったかは ID の並びで長くなるので、人数だけ残す。"""
    return f"members={len(group.members)}"


@router.get("", response_model=list[GroupResponse], dependencies=[_READ_GROUPS])
async def list_groups(
    members: TenantMembersDep,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> list[GroupResponse]:
    groups = members.groups()
    with_email = principal.can("group:manage")
    return [_to_response(g, with_email=with_email) for g in groups]


@router.get("/users", response_model=list[GroupMemberResponse], dependencies=[_MANAGE_GROUPS])
async def member_candidates(members: TenantMembersDep) -> list[GroupMemberResponse]:
    """所属に選べる利用者（自分のテナントの、有効な人だけ）。"""
    users = sorted(members.users(active_only=True), key=lambda u: (u.username, u.id))
    return [_member(u) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GroupResponse, dependencies=[_MANAGE_GROUPS])
async def create_group(body: GroupCreateRequest, members: TenantMembersDep, audit: AuditRecorderDep) -> GroupResponse:
    name = body.name.strip()
    _ensure_unique_name(members, name)
    group = members.new_group(name, body.description.strip())
    group.members = _resolve_members(members, body.member_ids)
    members.session.add(group)
    members.session.flush()
    audit.execute(
        AuditEventType.GROUP_CREATED,
        target=AuditTarget.of(AuditTargetType.GROUP, group.id),
        reason=_member_count(group),
    )
    return _to_response(group)


@router.put("/{group_id}", response_model=GroupResponse, dependencies=[_MANAGE_GROUPS])
async def update_group(
    group_id: int, body: GroupUpdateRequest, members: TenantMembersDep, audit: AuditRecorderDep
) -> GroupResponse:
    group = members.group(group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "group_not_found"})
    if body.name is not None:
        name = body.name.strip()
        _ensure_unique_name(members, name, except_id=group_id)
        group.name = name
    if body.description is not None:
        group.description = body.description.strip()
    if body.member_ids is not None:
        group.members = _resolve_members(members, body.member_ids)
    members.session.flush()
    audit.execute(
        AuditEventType.GROUP_UPDATED,
        target=AuditTarget.of(AuditTargetType.GROUP, group_id),
        reason=_member_count(group),
    )
    return _to_response(group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_MANAGE_GROUPS])
async def delete_group(group_id: int, members: TenantMembersDep, audit: AuditRecorderDep) -> None:
    group = members.group(group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "group_not_found"})
    # ⚠ SQLite は外部キーの CASCADE を既定で効かせない。所属は明示的に外す。
    group.members = []
    members.session.delete(group)
    audit.execute(
        AuditEventType.GROUP_DELETED,
        target=AuditTarget.of(AuditTargetType.GROUP, group_id),
    )


__all__ = ["router"]
