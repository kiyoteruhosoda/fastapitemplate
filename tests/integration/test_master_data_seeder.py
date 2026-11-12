"""Seeding master data (ADR-0078 §3).

One thing is watched: **a default administrator deleted during operation does not come back on a
re-seed that adds permissions.** If it did, an administrator with the publicly known default
password would silently reappear and keep running (happened in production of the derived app
blobshare on 2026-09-02).
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
    """**This is the key point.** Migrations that add permissions call only ``seed_master_data``."""
    session = _session(engine)
    admin = _admin(session)
    assert admin is not None  # seated by conftest
    admin.roles.clear()
    session.delete(admin)
    session.flush()

    seed_master_data(session)

    assert _admin(session) is None
    session.close()


def test_reseeding_still_adds_new_roles_and_permissions(engine: sa.Engine) -> None:
    """Even without creating the administrator, adding roles and permissions still works."""
    session = _session(engine)
    manager = session.scalar(sa.select(Role).where(Role.name == "manager"))
    assert manager is not None
    manager.permissions.clear()
    # ⚠ Before deleting the permission rows, **remove them from every role**. With foreign-key
    #    checks on (derived apps enable them even on SQLite), they cannot be deleted while
    #    references remain.
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
    """Re-seating is idempotent. If the admin already exists, the password is not written back."""
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
    """Recovery after losing the key (``scripts/seed_master_data.py``) works."""
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
    # Created with the given password (not the default hash).
    assert restored.password_hash != master_data.DEFAULT_ADMIN_PASSWORD_HASH
    session.close()
