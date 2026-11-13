"""The local entrance can be closed (ADR-0076 §3 decisions 2, 3).

``LOCAL_LOGIN_ENABLED=false`` stops password and passkey sign-in and **registration of local
credentials**. Registration is stopped too so that no spare key to the closed entrance can be made.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from presentation.fastapi.dependencies.local_login import ERROR_CODE
from shared.domain.auth import master_data


@pytest.fixture
def closed_client(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app with the local entrance closed."""
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
    """Blocking only passwords could be bypassed if the passkey entrance stayed open."""
    response = closed_client.post("/api/auth/passkey/challenge", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == ERROR_CODE


def test_password_reset_is_refused_when_closed(closed_client: TestClient) -> None:
    """Going through a reset would create a local password (a spare key to the closed entrance)."""
    response = closed_client.post("/api/auth/forgot-password", json={"email": "someone@example.com"})
    assert response.status_code == 403


def test_credentials_cannot_be_enrolled_when_closed(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when authenticated, passkeys and TOTP cannot be added while closed (ADR-0076 §3 decision 3)."""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "false")
    closed = TestClient(create_app())
    for path in ("/api/account/security/passkeys/registration", "/api/account/security/two-factor/enrollment"):
        response = closed.post(path, headers=admin_headers, json={})
        assert response.status_code == 403, path
        assert response.json()["detail"]["error"] == ERROR_CODE


def test_the_login_screen_is_told_the_entrance_is_closed(closed_client: TestClient) -> None:
    """The screen checks this and hides the password field and passkey button."""
    response = closed_client.get("/api/auth/sso/provider")
    assert response.status_code == 200
    assert response.json()["local_login_enabled"] is False


def test_everything_stays_open_by_default(client: TestClient) -> None:
    response = client.get("/api/auth/sso/provider")
    assert response.status_code == 200
    body = response.json()
    assert body["local_login_enabled"] is True
    # The template, which does not know its federation partner, defaults to "SSO disabled" (ADR-0077 §1).
    assert body["enabled"] is False
