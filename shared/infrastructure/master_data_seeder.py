"""マスタデータ投入（冪等）。

値の正本は ``shared/domain/auth/master_data.py``。ここには投入ロジックのみを
置き、``scripts/seed_master_data.py``・マイグレーション・テストから共用する。

⚠ **「ロール・権限を足す」と「初期管理者を据える」は別の操作**（ADR-0024）。
権限を足すマイグレーションは前者だけを呼ぶ。混ぜると、**運用の途中で消した
既定の管理者が、権限を 1 つ足すたびに既定のパスワードのまま復活する**。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import Permission, Role, User


def seed_master_data(session: Session) -> None:
    """ロール・権限を投入する。既存の行は変更しない（冪等）。

    **初期管理者は作らない**（``ensure_default_admin`` が担う。ADR-0024）。
    権限やロールを足すたびに呼ばれる関数なので、ここで利用者を作ると
    「消したはずの管理者が権限追加のたびに戻る」ことになる。
    """
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

    session.flush()


def ensure_default_admin(session: Session, *, password: str | None = None) -> None:
    """初期管理者が居なければ据える（冪等）。

    **据え付けと、鍵を失ったときの復旧でだけ呼ぶ**（ADR-0024）。呼ぶのは
    最初のマイグレーション（``0002_seed_master_data``）と
    ``scripts/seed_master_data.py`` の 2 か所。

    ⚠ **``password`` を渡さないと、公開されている既定のハッシュで作る**
    （平文は ``master_data.DEFAULT_ADMIN_PASSWORD``）。据え付け直後に変える前提の
    値なので、**動いている環境から呼ばない**こと。
    """
    if session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)) is not None:
        return

    role = session.scalar(select(Role).where(Role.name == master_data.DEFAULT_ADMIN_ROLE))
    if role is None:
        raise RuntimeError("roles are not seeded yet; call seed_master_data first")

    admin = User(
        id=master_data.DEFAULT_ADMIN_ID,
        email=master_data.DEFAULT_ADMIN_EMAIL,
        username=master_data.DEFAULT_ADMIN_USERNAME,
        password_hash=generate_password_hash(password) if password else master_data.DEFAULT_ADMIN_PASSWORD_HASH,
        is_active=True,
    )
    admin.roles.append(role)
    session.add(admin)
    session.flush()


__all__ = ["ensure_default_admin", "seed_master_data"]
