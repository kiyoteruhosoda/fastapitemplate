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
    """⚠ Tokens are not put in the body (ADR-0076 §4).

    Cookies are sent automatically, so returning tokens in the body too would let XSS call the refresh
    entrance and read a new token, defeating the point of ``httpOnly``.
    """
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"expires_in": body["expires_in"]}, body
    assert client.cookies[ACCESS_TOKEN_COOKIE]
    assert client.cookies[REFRESH_TOKEN_COOKIE]
    # Only the CSRF double-submit token needs to be readable from JavaScript.
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
    # Issued in the same second, the values themselves can match (`iat` / `exp` have second resolution).
    # What is checked is "whether it was set again".
    issued = response.headers.get_list("set-cookie")
    assert any(cookie.startswith(f"{ACCESS_TOKEN_COOKIE}=") for cookie in issued)
    assert any(cookie.startswith(f"{REFRESH_TOKEN_COOKIE}=") for cookie in issued)


def test_refresh_without_the_cookie_is_refused(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_rejects_an_access_token_in_the_refresh_cookie(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The refresh entrance accepts only refresh tokens (it checks the type)."""
    access = client.cookies[ACCESS_TOKEN_COOKIE]
    # Delete the real one before injecting (leaving it sends two with the same name, and which is read depends on order)
    client.cookies.delete(REFRESH_TOKEN_COOKIE)
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
    # The scope does not change
    assert "user:manage" in data["scopes"]
    # Existing tokens are looked up again by user_id, so they stay valid after the change and /me reflects it
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert me["email"] == "renamed@example.com"
    # The next sign-in uses the new email address
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
    # Mail sending is disabled, so the token is taken directly from the DB for verification
    client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})
    row = db_session.scalar(select(PasswordResetToken))
    assert row is not None

    # Only the hash of the plaintext token is stored, so reissue it using the service directly
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
    # The token is single-use
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
