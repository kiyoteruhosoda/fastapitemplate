from sqlalchemy import select

from shared.infrastructure.models import PasswordResetToken, User


def test_login_success(client) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "admin"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]


def test_login_wrong_password(client) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_me_requires_authentication(client) -> None:
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_scopes(client, admin_headers) -> None:
    response = client.get("/api/auth/me", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@example.com"
    assert "user:manage" in data["scopes"]


def test_refresh_issues_new_pair(client) -> None:
    login = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "admin"}
    ).json()
    response = client.post(
        "/api/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_refresh_rejects_access_token(client) -> None:
    login = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "admin"}
    ).json()
    response = client.post(
        "/api/auth/refresh", json={"refresh_token": login["access_token"]}
    )
    assert response.status_code == 401


def test_change_password_roundtrip(client, admin_headers) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "admin", "new_password": "new-password-1"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "new-password-1"},
        ).status_code
        == 200
    )


def test_change_password_wrong_current(client, admin_headers) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "wrong", "new_password": "new-password-1"},
    )
    assert response.status_code == 400


def test_forgot_password_does_not_leak_user_existence(client) -> None:
    known = client.post(
        "/api/auth/forgot-password", json={"email": "admin@example.com"}
    )
    unknown = client.post(
        "/api/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"status": "accepted"}


def test_reset_password_with_valid_token(client, db_session) -> None:
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


def test_reset_password_with_invalid_token(client) -> None:
    response = client.post(
        "/api/auth/reset-password",
        json={"token": "bogus", "new_password": "whatever-123"},
    )
    assert response.status_code == 400


def test_inactive_user_cannot_login(client, db_session) -> None:
    user = db_session.scalar(select(User).where(User.email == "admin@example.com"))
    user.is_active = False
    db_session.commit()
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "admin"}
    )
    assert response.status_code == 401
