"""システム管理者（テナントの外側の人。ADR-0061・ADR-0063）を作る。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import Role, User


def create_system_administrator(session: Session, *, email: str, username: str, password: str) -> bool:
    """テナントに属さない ``system-admin`` を作る。同じメールアドレスの人が居れば作らず ``False``。"""
    if session.scalar(sa.select(User.id).where(User.email == email)) is not None:
        return False
    user = User(email=email, username=username, password_hash=generate_password_hash(password), is_active=True)
    user.roles = list(session.scalars(sa.select(Role).where(Role.name.in_(list(master_data.SYSTEM_ROLES)))))
    session.add(user)
    session.flush()
    return True


__all__ = ["create_system_administrator"]
