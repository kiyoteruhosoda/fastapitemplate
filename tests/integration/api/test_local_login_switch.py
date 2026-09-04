"""ローカルの入口を閉じられること（ADR-0026 決定 2・3）。

``LOCAL_LOGIN_ENABLED=false`` で、パスワード・パスキーのログインと**ローカル資格情報の
登録**が止まる。登録まで止めるのは、閉じた入口の合鍵を作れないようにするため。
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from presentation.fastapi.dependencies.local_login import ERROR_CODE
from shared.domain.auth import master_data


@pytest.fixture
def closed_client(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """ローカルの入口を閉じたアプリ。"""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "false")
    return TestClient(create_app())


def test_password_login_is_refused_when_closed(closed_client: TestClient) -> None:
    response = closed_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == ERROR_CODE


def test_passkey_login_is_refused_when_closed(closed_client: TestClient) -> None:
    """パスワードだけ塞いでも、パスキーの口が開いていれば迂回できてしまう。"""
    response = closed_client.post("/api/auth/passkey/challenge", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == ERROR_CODE


def test_password_reset_is_refused_when_closed(closed_client: TestClient) -> None:
    """再設定を通すとローカルのパスワードが作れてしまう（閉じた入口の合鍵）。"""
    response = closed_client.post("/api/auth/forgot-password", json={"email": "someone@example.com"})
    assert response.status_code == 403


def test_credentials_cannot_be_enrolled_when_closed(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """認証済みでも、閉じている間はパスキー・TOTP を足せない（ADR-0026 決定 3）。"""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "false")
    closed = TestClient(create_app())
    for path in ("/api/account/security/passkeys/registration", "/api/account/security/two-factor/enrollment"):
        response = closed.post(path, headers=admin_headers, json={})
        assert response.status_code == 403, path
        assert response.json()["detail"]["error"] == ERROR_CODE


def test_the_login_screen_is_told_the_entrance_is_closed(closed_client: TestClient) -> None:
    """画面はここを見てパスワード欄とパスキーのボタンを出さない。"""
    response = closed_client.get("/api/auth/sso/provider")
    assert response.status_code == 200
    assert response.json()["local_login_enabled"] is False


def test_everything_stays_open_by_default(client: TestClient) -> None:
    response = client.get("/api/auth/sso/provider")
    assert response.status_code == 200
    body = response.json()
    assert body["local_login_enabled"] is True
    # 連携先を知らないテンプレートの既定は「SSO 無効」（ADR-0025）。
    assert body["enabled"] is False
