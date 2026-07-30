"""二要素認証（TOTP）の登録・ログイン・解除。"""

from __future__ import annotations

import httpx
import pyotp
import pytest
from fastapi.testclient import TestClient


def _login(client: TestClient, **extra: object) -> httpx.Response:
    return client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin", **extra},
    )


@pytest.fixture
def enrolled_secret(client: TestClient, admin_headers: dict[str, str]) -> str:
    """管理者の二要素認証を有効化し、共有鍵を返す。"""
    enrollment = client.post("/api/account/security/two-factor/enrollment", headers=admin_headers)
    assert enrollment.status_code == 200, enrollment.text
    secret = str(enrollment.json()["secret"])

    confirmation = client.post(
        "/api/account/security/two-factor/confirmation",
        headers=admin_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmation.status_code == 200, confirmation.text
    return secret


def test_status_requires_authentication(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/account/security/two-factor").status_code == 401


def test_enrollment_is_not_enabled_until_confirmed(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post("/api/account/security/two-factor/enrollment", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["qr_code"].startswith("data:image/svg+xml;base64,")

    status = client.get("/api/account/security/two-factor", headers=admin_headers)
    assert status.json() == {"enabled": False, "enrolling": True}

    # 確認前はログインにコードを要求しない（登録を中断しても締め出されない）
    assert _login(client).status_code == 200


def test_confirmation_enables_two_factor(
    client: TestClient, admin_headers: dict[str, str], enrolled_secret: str
) -> None:
    status = client.get("/api/account/security/two-factor", headers=admin_headers)
    assert status.json() == {"enabled": True, "enrolling": False}


def test_confirmation_rejects_wrong_code(client: TestClient, admin_headers: dict[str, str]) -> None:
    client.post("/api/account/security/two-factor/enrollment", headers=admin_headers)
    response = client.post(
        "/api/account/security/two-factor/confirmation",
        headers=admin_headers,
        json={"code": "000000"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_totp"


def test_login_requires_code_once_enabled(client: TestClient, enrolled_secret: str) -> None:
    response = _login(client)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "totp_required"


def test_login_rejects_wrong_code(client: TestClient, enrolled_secret: str) -> None:
    response = _login(client, totp_code="000000")
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_totp"


def test_login_succeeds_with_code(client: TestClient, enrolled_secret: str) -> None:
    response = _login(client, totp_code=pyotp.TOTP(enrolled_secret).now())
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_second_enrollment_is_rejected_while_enabled(
    client: TestClient, admin_headers: dict[str, str], enrolled_secret: str
) -> None:
    response = client.post("/api/account/security/two-factor/enrollment", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "totp_already_enabled"


def test_removal_requires_a_valid_code(client: TestClient, admin_headers: dict[str, str], enrolled_secret: str) -> None:
    rejected = client.post(
        "/api/account/security/two-factor/removal",
        headers=admin_headers,
        json={"code": "000000"},
    )
    assert rejected.status_code == 400

    accepted = client.post(
        "/api/account/security/two-factor/removal",
        headers=admin_headers,
        json={"code": pyotp.TOTP(enrolled_secret).now()},
    )
    assert accepted.status_code == 200
    assert _login(client).status_code == 200
