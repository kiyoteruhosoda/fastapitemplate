"""パスワードを変えたら、それより前に始まったログインを終わらせる（ADR-0057）。

更新トークンはサーバーに控えが無く、署名だけで確かめている。区切りが無いと、
パスワードを変えても盗まれた更新トークンは寿命（既定 14 日）いっぱい使える。

「盗まれた側」のセッションは ``other_client`` が**少し前に**張ったものとして作る。
``iat`` は秒までしか持たないので、同じ秒の中で出したトークンは区切りでは落ちない。
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.domain.auth import master_data
from shared.infrastructure.models import PasswordResetToken, User
from tests.conftest import sign_in

_EMAIL = master_data.DEFAULT_ADMIN_EMAIL
_PASSWORD = master_data.DEFAULT_ADMIN_PASSWORD


@contextmanager
def _issued_earlier(seconds: int) -> Iterator[None]:
    """この中で出したトークンの ``iat`` を、*seconds* 秒前にする。"""
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = datetime.now(UTC) - timedelta(seconds=seconds)
    with patch("presentation.fastapi.services.token_service.datetime", clock):
        yield


def _refresh(client: TestClient) -> int:
    return client.post("/api/auth/refresh", headers={CSRF_HEADER: client.cookies[CSRF_COOKIE]}).status_code


def _stolen_session(other_client: TestClient, email: str, password: str) -> None:
    """盗まれた側のセッション。パスワードを変えるより前に張られている。"""
    # ⚠ 更新も時計を戻したまま行う。戻さずに更新すると、新しいトークンに入れ替わって
    #   「前に始まったログイン」ではなくなる
    with _issued_earlier(10):
        sign_in(other_client, email, password)
        assert _refresh(other_client) == 200


def test_changing_the_password_ends_earlier_sessions_but_keeps_this_one(
    client: TestClient, other_client: TestClient
) -> None:
    _stolen_session(other_client, _EMAIL, _PASSWORD)
    headers = sign_in(client, _EMAIL, _PASSWORD)

    changed = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": _PASSWORD, "new_password": "new-password-1"},
    )
    assert changed.status_code == 200, changed.text

    # 盗まれた側は、更新もトークンの出し直しもできない
    assert _refresh(other_client) == 401
    switched = other_client.post(
        "/api/auth/switch-role", headers={CSRF_HEADER: other_client.cookies[CSRF_COOKIE]}, json={"role": None}
    )
    assert switched.status_code == 401
    # 変えた本人のこのセッションは、出し直したトークンで続く
    assert _refresh(client) == 200
    assert client.get("/api/auth/me").status_code == 200


def test_resetting_the_password_ends_earlier_sessions(
    client: TestClient, other_client: TestClient, db_session: Session
) -> None:
    _stolen_session(other_client, _EMAIL, _PASSWORD)
    client.post("/api/auth/forgot-password", json={"email": _EMAIL})
    row = db_session.scalar(select(PasswordResetToken))
    assert row is not None
    # 平文はハッシュしか残らないので、既知の値で置き直す
    token = secrets.token_urlsafe(32)
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    db_session.commit()

    reset = client.post("/api/auth/reset-password", json={"token": token, "new_password": "reset-password-1"})
    assert reset.status_code == 200, reset.text

    assert _refresh(other_client) == 401
    # 新しいパスワードでは入り直せる
    sign_in(client, _EMAIL, "reset-password-1")
    assert _refresh(client) == 200


def test_an_administrator_setting_the_password_ends_the_users_sessions(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "taken-over@example.com", "username": "taken", "password": "before-password-1", "roles": []},
    )
    assert created.status_code == 201, created.text
    _stolen_session(other_client, "taken-over@example.com", "before-password-1")

    user = db_session.scalar(select(User).where(User.email == "taken-over@example.com"))
    assert user is not None
    updated = client.put(f"/api/admin/users/{user.id}", headers=admin_headers, json={"password": "after-password-1"})
    assert updated.status_code == 200, updated.text

    assert _refresh(other_client) == 401


def test_changes_other_than_the_password_keep_sessions(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    """名前を変えただけでは区切らない（区切るのはパスワードを変えたときだけ）。"""
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "renamed@example.com", "username": "before", "password": "a-password-1", "roles": []},
    )
    assert created.status_code == 201, created.text
    _stolen_session(other_client, "renamed@example.com", "a-password-1")

    user = db_session.scalar(select(User).where(User.email == "renamed@example.com"))
    assert user is not None
    updated = client.put(f"/api/admin/users/{user.id}", headers=admin_headers, json={"username": "after"})
    assert updated.status_code == 200, updated.text

    assert _refresh(other_client) == 200
