"""マスタデータの投入（ADR-0024）。

見張りたいのは 1 点。**運用の途中で消した既定の管理者が、権限を足す再投入で
復活しないこと。** 復活すると、公開されている既定のパスワードを持つ管理者が
黙って生えたまま動き続ける（派生アプリ blobshare の本番で 2026-09-02 に起きた）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from shared.domain.auth import master_data
from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
from shared.infrastructure.models import Permission, Role, User


def _session(engine: sa.Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _admin(session: Session) -> User | None:
    return session.scalar(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))


def test_reseeding_does_not_resurrect_a_deleted_admin(engine: sa.Engine) -> None:
    """**ここが要。** 権限を足すマイグレーションは ``seed_master_data`` だけを呼ぶ。"""
    session = _session(engine)
    admin = _admin(session)
    assert admin is not None  # conftest が据えている
    admin.roles.clear()
    session.delete(admin)
    session.flush()

    seed_master_data(session)

    assert _admin(session) is None
    session.close()


def test_reseeding_still_adds_new_roles_and_permissions(engine: sa.Engine) -> None:
    """管理者を作らなくなっても、ロールと権限の追加は効く。"""
    session = _session(engine)
    manager = session.scalar(sa.select(Role).where(Role.name == "manager"))
    assert manager is not None
    manager.permissions.clear()
    # ⚠ 権限の行を消す前に、**どのロールからも外す**。外部キーを検査する設定
    #    （派生アプリでは SQLite でも有効にしている）だと、参照が残ったままでは
    #    消せない。
    for role in session.scalars(sa.select(Role)):
        role.permissions = [item for item in role.permissions if item.code != "audit:view"]
    session.flush()
    session.execute(sa.delete(Permission).where(Permission.code == "audit:view"))
    session.flush()

    seed_master_data(session)

    restored = session.scalar(sa.select(Role).where(Role.name == "manager"))
    assert restored is not None
    assert {permission.code for permission in restored.permissions} == set(master_data.ROLE_PERMISSIONS["manager"])
    assert session.scalar(sa.select(Permission).where(Permission.code == "audit:view")) is not None
    session.close()


def test_the_default_admin_is_only_added_when_missing(engine: sa.Engine) -> None:
    """据え直しは冪等。既に居るならパスワードを書き戻さない。"""
    session = _session(engine)
    admin = _admin(session)
    assert admin is not None
    admin.password_hash = "changed-by-the-operator"
    session.flush()

    ensure_default_admin(session, password="another-password")

    refreshed = _admin(session)
    assert refreshed is not None
    assert refreshed.password_hash == "changed-by-the-operator"
    session.close()


def test_the_default_admin_can_be_put_back_for_recovery(engine: sa.Engine) -> None:
    """鍵を失ったときの復旧（``scripts/seed_master_data.py``）は通る。"""
    session = _session(engine)
    admin = _admin(session)
    assert admin is not None
    admin.roles.clear()
    session.delete(admin)
    session.flush()

    ensure_default_admin(session, password="recovered-password")

    restored = _admin(session)
    assert restored is not None
    assert restored.is_active is True
    assert [role.name for role in restored.roles] == [master_data.DEFAULT_ADMIN_ROLE]
    # 渡したパスワードで作る（既定のハッシュを使わない）。
    assert restored.password_hash != master_data.DEFAULT_ADMIN_PASSWORD_HASH
    session.close()
