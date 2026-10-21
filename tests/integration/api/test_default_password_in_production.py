"""本番では、公開されている既定のパスワードで入れない（ADR-0056）。

既定の管理者は ``ADMIN_INITIAL_PASSWORD`` を渡し忘れると、リポジトリに載っている
パスワードのまま全権で据わる。渡し忘れを「誰でも入れる」ではなく「誰も入れない」に倒す。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import User
from shared.kernel.settings.secret_guard import PRODUCTION


def _login(client: TestClient, password: str) -> int:
    response = client.post("/api/auth/login", json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": password})
    return response.status_code


def test_production_refuses_the_published_default_password(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", PRODUCTION)
    response = client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert response.status_code == 401
    # 理由は他の失敗と同じにそろえる（アカウントの存在や状態を漏らさない）
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_production_accepts_a_password_that_was_changed(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = db_session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    assert user is not None
    user.password_hash = generate_password_hash("a-password-that-was-changed")
    db_session.commit()
    monkeypatch.setenv("APP_ENV", PRODUCTION)
    assert _login(client, "a-password-that-was-changed") == 200


def test_development_still_accepts_the_default_password(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """開発では据え付け直後に今までどおり入れる（README の手順どおり）。"""
    monkeypatch.setenv("APP_ENV", "development")
    assert _login(client, master_data.DEFAULT_ADMIN_PASSWORD) == 200
