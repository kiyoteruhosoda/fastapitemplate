"""使えなくなったパスワード再設定トークンの掃除（ADR-0097）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from presentation.fastapi.services.password_token_purge import purge_spent_password_tokens_once
from shared.domain.auth import master_data
from shared.infrastructure.models import PasswordResetToken, User
from shared.kernel.timestamps import utcnow

_LIVE = "live-token"


def _admin(session: Session) -> User:
    return session.scalars(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)).one()


def _add(session: Session, token: str, *, expires_at: datetime, used_at: datetime | None = None) -> None:
    session.add(
        PasswordResetToken(
            user_id=_admin(session).id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=expires_at,
            used_at=used_at,
        )
    )
    session.commit()


def _hashes(session: Session) -> list[str]:
    return list(session.scalars(sa.select(PasswordResetToken.token_hash)).all())


def test_expired_and_used_rows_are_removed(db_session: Session) -> None:
    now = utcnow()
    _add(db_session, "expired", expires_at=now - timedelta(seconds=1))
    _add(db_session, "used", expires_at=now + timedelta(hours=1), used_at=now - timedelta(minutes=1))
    _add(db_session, _LIVE, expires_at=now + timedelta(hours=1))

    assert purge_spent_password_tokens_once() == 2
    db_session.expire_all()
    assert _hashes(db_session) == [hashlib.sha256(_LIVE.encode()).hexdigest()]
    assert purge_spent_password_tokens_once() == 0


def test_a_live_token_still_resets_the_password_after_the_purge(client: TestClient, db_session: Session) -> None:
    _add(db_session, _LIVE, expires_at=utcnow() + timedelta(hours=1))
    purge_spent_password_tokens_once()

    response = client.post("/api/auth/reset-password", json={"token": _LIVE, "new_password": "a-new-password-1"})

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert check_password_hash(_admin(db_session).password_hash or "", "a-new-password-1")
