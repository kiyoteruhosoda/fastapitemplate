"""システム管理者（テナントの外側の人。ADR-0079 §1・§3）を作る。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import Role, User
from shared.infrastructure.sign_in_directory import email_taken


def create_system_administrator(session: Session, *, email: str, username: str, password: str) -> bool:
    """テナントに属さない ``system-admin`` を作る。同じメールアドレスの人が居れば作らず ``False``。"""
    if email_taken(session, email, None):
        return False
    user = User(email=email, username=username, password_hash=generate_password_hash(password), is_active=True)
    user.roles = list(session.scalars(sa.select(Role).where(Role.name == master_data.SYSTEM_ADMIN_ROLE)))
    session.add(user)
    session.flush()
    return True


__all__ = ["create_system_administrator"]
