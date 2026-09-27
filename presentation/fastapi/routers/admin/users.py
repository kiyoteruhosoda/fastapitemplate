"""ユーザー管理 API（要 ``user:manage``）。

作成・更新・削除は監査ログ（``audit_log``）へ残す。``reason`` には**変更した項目名**
だけを入れ、値そのもの（メールアドレス・パスワード）は入れない（ADR-0013）。

一覧は **「この利用者が入れる手段」**（``entrances``）も返す（ADR-0039）。認証系が
2 つある以上、開いている口の数は並べて見ないと分からない。材料は
**それぞれのコンテキストに聞く** ——パスワードは ``users`` の列、TOTP と
パスキーは account_security、IdP との結び付きは identity_federation。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
from presentation.fastapi.schemas.admin import (
    SignInEntrances,
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


@dataclass(frozen=True)
class _Inventory:
    """棚卸しの材料。全員分をまとめて引き、利用者ごとに引き直さない。"""

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
        """作った直後の利用者。第二要素も結び付きもまだ無い。"""
        return cls(factors={}, issuers={})

    def entrances_of(self, user: User) -> SignInEntrances:
        factors = self.factors.get(user.id, LocalFactors())
        return SignInEntrances(
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


def _resolve_roles(db: Session, names: list[str]) -> list[Role]:
    roles = db.scalars(select(Role).where(Role.name.in_(names))).all()
    missing = set(names) - {r.name for r in roles}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_roles", "roles": sorted(missing)},
        )
    return list(roles)


def _changed_fields(body: UserUpdateRequest) -> str:
    """監査ログの ``reason`` に載せる「何を変えたか」。値そのものは載せない。"""
    fields = sorted(name for name, value in body.model_dump().items() if value is not None)
    return f"fields={','.join(fields)}" if fields else "fields=none"


@router.get("", response_model=list[UserResponse])
async def list_users(db: DbDep) -> list[UserResponse]:
    users = db.scalars(select(User).order_by(User.id)).all()
    inventory = _Inventory.of(db)
    return [_to_response(u, inventory) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(body: UserCreateRequest, db: DbDep, audit: AuditRecorderDep) -> UserResponse:
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
    audit.execute(
        AuditEventType.USER_CREATED,
        target=AuditTarget.of(AuditTargetType.USER, user.id),
    )
    return _to_response(user, _Inventory.none())


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: DbDep,
    audit: AuditRecorderDep,
) -> UserResponse:
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
    audit.execute(
        AuditEventType.USER_UPDATED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
        reason=_changed_fields(body),
    )
    return _to_response(user, _Inventory.of(db))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbDep, audit: AuditRecorderDep) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "user_not_found"})
    user.roles = []
    db.delete(user)
    audit.execute(
        AuditEventType.USER_DELETED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
    )
