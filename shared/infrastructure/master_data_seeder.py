"""Seeding master data (idempotent).

The values live in ``shared/domain/auth/master_data.py``. Only the seeding logic is here, shared
by ``scripts/seed_master_data.py``, migrations and tests.

⚠ **"Adding roles/permissions" and "seating the initial administrator" are separate operations**
(ADR-0078 §3). Migrations that add permissions call only the former. Mixing them means **a default
administrator deleted during operation comes back, with the default password, every time a
permission is added**.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import Permission, Role, User


def seed_master_data(session: Session) -> None:
    """Seed roles and permissions. Existing rows are not changed (idempotent).

    **Does not create the initial administrator** (``ensure_default_admin`` does; ADR-0078 §3).
    This function is called every time permissions or roles are added, so creating users here
    would mean "an administrator that was deleted comes back with every permission addition".
    """
    roles: dict[str, Role] = {}
    for role_id, name in master_data.ROLES:
        role = session.scalar(select(Role).where(Role.name == name))
        if role is None:
            # The fixed id may already be taken by a role added during operation.
            # Then let the DB assign one (the name is the stable key; the id is only for references).
            taken = session.get(Role, role_id) is not None
            role = Role(name=name) if taken else Role(id=role_id, name=name)
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
    """Seat the initial administrator if there is none (idempotent).

    **Call only at setup and for recovery after losing the key** (ADR-0078 §3). It is called
    from two places: the first migration (``0002_seed_master_data``) and
    ``scripts/seed_master_data.py``.

    ⚠ **Without ``password``, it is created with the published default hash**
    (plaintext ``master_data.DEFAULT_ADMIN_PASSWORD``). That value is meant to be changed right
    after setup, so **never call this from a running environment**.
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
