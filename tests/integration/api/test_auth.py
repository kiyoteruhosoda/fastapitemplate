from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_COOKIE_PATH,
    REFRESH_TOKEN_COOKIE,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE
from shared.domain.auth import master_data
from shared.infrastructure.models import PasswordResetToken, User


def test_login_puts_the_tokens_in_cookies_and_not_in_the_body(client: TestClient) -> None:
    """⚠ 本文にトークンを載せない（ADR-0028）。

    Cookie は自動で送られるので、本文にも返すと XSS が更新の口を叩いて新しい
    トークンを読めてしまい、``httpOnly`` にした意味が無くなる。
    """
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"expires_in": body["expires_in"]}, body
    assert client.cookies[ACCESS_TOKEN_COOKIE]
    assert client.cookies[REFRESH_TOKEN_COOKIE]
    # CSRF の二重送信トークンだけは JavaScript から読める必要がある。
    assert client.cookies[CSRF_COOKIE]


def test_login_wrong_password(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_me_requires_authentication(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_scopes(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/auth/me", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@example.com"
    assert "user:manage" in data["scopes"]


def test_refresh_reads_the_cookie_and_issues_a_new_pair(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post("/api/auth/refresh", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["expires_in"] > 0
    # 値そのものは同じ秒に発行すると一致しうる（`iat` / `exp` が秒解像度）。
    # 見るのは「載せ直したか」。
    issued = response.headers.get_list("set-cookie")
    assert any(cookie.startswith(f"{ACCESS_TOKEN_COOKIE}=") for cookie in issued)
    assert any(cookie.startswith(f"{REFRESH_TOKEN_COOKIE}=") for cookie in issued)


def test_refresh_without_the_cookie_is_refused(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_rejects_an_access_token_in_the_refresh_cookie(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """更新の口はリフレッシュトークンしか受け取らない（種別を見ている）。"""
    access = client.cookies[ACCESS_TOKEN_COOKIE]
    client.cookies.set(REFRESH_TOKEN_COOKIE, access, path=REFRESH_COOKIE_PATH)
    assert client.post("/api/auth/refresh", headers=admin_headers).status_code == 401


def test_update_me_changes_email_and_username(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/auth/me",
        headers=admin_headers,
        json={"email": "renamed@example.com", "username": "renamed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "renamed@example.com"
    assert data["username"] == "renamed"
    # scope は変わらない
    assert "user:manage" in data["scopes"]
    # 既存トークンは user_id で引き直すため変更後も有効で、/me に反映される
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert me["email"] == "renamed@example.com"
    # 次回のログインは新しいメールアドレスで行う
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "renamed@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD},
        ).status_code
        == 200
    )


def test_update_me_rejects_taken_email(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "other@example.com", "username": "other", "password": "password-123", "roles": ["member"]},
    )
    assert created.status_code == 201
    response = client.put(
        "/api/auth/me",
        headers=admin_headers,
        json={"email": "other@example.com", "username": "admin"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "email_already_exists"


def test_update_me_keeping_own_email_is_allowed(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/auth/me",
        headers=admin_headers,
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "username": "display-name"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "display-name"


def test_update_me_requires_authentication(client: TestClient) -> None:
    client.cookies.clear()
    response = client.put("/api/auth/me", json={"email": "a@example.com", "username": "a"})
    assert response.status_code == 401


def test_change_password_roundtrip(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": master_data.DEFAULT_ADMIN_PASSWORD, "new_password": "new-password-1"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "new-password-1"},
        ).status_code
        == 200
    )


def test_change_password_wrong_current(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "wrong", "new_password": "new-password-1"},
    )
    assert response.status_code == 400


def test_forgot_password_does_not_leak_user_existence(client: TestClient) -> None:
    known = client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"status": "accepted"}


def test_reset_password_with_valid_token(client: TestClient, db_session: Session) -> None:
    # メール送信は無効のためトークンは DB から直接取り出して検証する
    client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})
    row = db_session.scalar(select(PasswordResetToken))
    assert row is not None

    # 平文トークンはハッシュしか保存されないため、サービスを直接使って発行し直す
    import hashlib
    import secrets

    token = secrets.token_urlsafe(32)
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    db_session.commit()

    response = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "reset-password-1"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "reset-password-1"},
        ).status_code
        == 200
    )
    # トークンは使い捨て
    again = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "another-password-1"},
    )
    assert again.status_code == 400


def test_reset_password_with_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/api/auth/reset-password",
        json={"token": "bogus", "new_password": "whatever-123"},
    )
    assert response.status_code == 400


def test_inactive_user_cannot_login(client: TestClient, db_session: Session) -> None:
    user = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert user is not None
    user.is_active = False
    db_session.commit()
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD}
    )
    assert response.status_code == 401
