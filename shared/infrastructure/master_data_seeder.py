"""マスタデータ投入（冪等）。

値の正本は ``shared/domain/auth/master_data.py``。ここには投入ロジックのみを
置き、``scripts/seed_master_data.py``・マイグレーション・テストから共用する。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import Permission, Role, User


def seed_master_data(session: Session, *, admin_password: str | None = None) -> None:
    """ロール・権限・初期管理者を投入する。既存の行は変更しない（冪等）。"""
    roles: dict[str, Role] = {}
    for role_id, name in master_data.ROLES:
        role = session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(id=role_id, name=name)
            session.add(role)
        roles[name] = role

    permissions: dict[str, Permission] = {}
    for code in master_data.PERMISSION_CODES:
        permission = session.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code)
            session.add(permission)
        permissions[code] = permission
    session.flush()

    for role_name, codes in master_data.ROLE_PERMISSIONS.items():
        role = roles[role_name]
        existing = {p.code for p in role.permissions}
        for code in codes:
            if code not in existing:
                role.permissions.append(permissions[code])

    admin = session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    if admin is None:
        password_hash = (
            generate_password_hash(admin_password) if admin_password else master_data.DEFAULT_ADMIN_PASSWORD_HASH
        )
        admin = User(
            id=master_data.DEFAULT_ADMIN_ID,
            email=master_data.DEFAULT_ADMIN_EMAIL,
            username=master_data.DEFAULT_ADMIN_USERNAME,
            password_hash=password_hash,
            is_active=True,
        )
        admin.roles.append(roles[master_data.DEFAULT_ADMIN_ROLE])
        session.add(admin)

    session.flush()


__all__ = ["seed_master_data"]
