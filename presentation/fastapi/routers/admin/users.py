"""ユーザー管理 API（要 ``user:manage``）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import (
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from shared.infrastructure.models import Role, User
from shared.kernel.database.session import get_db

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin"],
    dependencies=[Depends(require_permission("user:manage"))],
)

DbDep = Annotated[Session, Depends(get_db)]


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        roles=sorted(r.name for r in user.roles),
    )


def _resolve_roles(db: Session, names: list[str]) -> list[Role]:
    roles = db.scalars(select(Role).where(Role.name.in_(names))).all()
    missing = set(names) - {r.name for r in roles}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_roles", "roles": sorted(missing)},
        )
    return list(roles)


@router.get("", response_model=list[UserResponse])
async def list_users(db: DbDep) -> list[UserResponse]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [_to_response(u) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(body: UserCreateRequest, db: DbDep) -> UserResponse:
    if db.scalar(select(User).where(User.email == body.email)):
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
    user.roles = _resolve_roles(db, body.roles)
    db.add(user)
    db.flush()
    return _to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, body: UserUpdateRequest, db: DbDep) -> UserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    if body.username is not None:
        user.username = body.username
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.roles is not None:
        user.roles = _resolve_roles(db, body.roles)
    if body.password is not None:
        user.password_hash = generate_password_hash(body.password)
    db.flush()
    return _to_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbDep) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    user.roles = []
    db.delete(user)
