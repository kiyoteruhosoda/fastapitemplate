"""アプリ（assay に直接ログイン）の assay のアクセストークンで、アプリ向けの口を叩く（ADR-0045）。"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.identity_federation.domain.exceptions import AppAccessTokenRejectedError
from bounded_contexts.identity_federation.presentation.app_bearer import app_token_gateway

_ISSUER = "https://idp.example.test/tenant"
_APP = "exampleapp"
_SUBJECT = "01a0-alice"


class _StubAppTokenGateway:
    """トークンの文字列そのものを「どのクレームか」の名前として扱う。"""

    def __init__(self) -> None:
        self.tokens: dict[str, dict[str, Any]] = {}
        self.userinfo_calls = 0

    def issue(self, name: str, **overrides: Any) -> str:
        claims = {"iss": _ISSUER, "sub": _SUBJECT, "client_id": _APP, "iat": int(time.time()), **overrides}
        self.tokens[name] = claims
        return name

    def verify_access_token(self, issuer: str, token: str) -> Mapping[str, Any]:
        assert issuer == _ISSUER
        if token not in self.tokens:
            raise AppAccessTokenRejectedError
        return self.tokens[token]

    def userinfo(self, issuer: str, token: str) -> Mapping[str, Any]:
        self.userinfo_calls += 1
        return {"sub": _SUBJECT, "email": "alice@example.com", "email_verified": True, "name": "alice"}


@pytest.fixture
def gateway() -> _StubAppTokenGateway:
    return _StubAppTokenGateway()


@pytest.fixture
def app_client(
    engine: sa.Engine, gateway: _StubAppTokenGateway, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_AUTO_PROVISION", "true")
    monkeypatch.setenv("OIDC_DEFAULT_ROLES", '["member"]')
    monkeypatch.setenv("APP_CLIENT_IDS", f'["{_APP}"]')
    app: FastAPI = create_app()
    app.dependency_overrides[app_token_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_first_visit_from_the_app_creates_the_account_once(
    app_client: TestClient, gateway: _StubAppTokenGateway
) -> None:
    token = gateway.issue("t1")

    first = app_client.get("/api/app/me", headers=_bearer(token))
    assert first.status_code == 200, first.text
    assert first.json()["email"] == "alice@example.com"

    # 2 回目からは結び付きで引く（userinfo を引き直さない）
    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 200
    assert gateway.userinfo_calls == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_id": "some-other-rp"},
        {"sub_type": "client"},
    ],
)
def test_tokens_for_other_clients_or_machines_are_rejected(
    app_client: TestClient, gateway: _StubAppTokenGateway, overrides: dict[str, Any]
) -> None:
    token = gateway.issue("t1", **overrides)

    response = app_client.get("/api/app/me", headers=_bearer(token))
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_token"


def test_unknown_tokens_are_rejected(app_client: TestClient) -> None:
    assert app_client.get("/api/app/me", headers=_bearer("garbage")).status_code == 401


def test_app_tokens_do_not_open_the_admin_api(app_client: TestClient, gateway: _StubAppTokenGateway) -> None:
    token = gateway.issue("t1")
    app_client.get("/api/app/me", headers=_bearer(token))

    assert app_client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_nothing_is_accepted_without_app_client_ids(
    app_client: TestClient, gateway: _StubAppTokenGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_CLIENT_IDS")
    token = gateway.issue("t1")

    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 401


def test_a_stop_from_the_idp_rejects_tokens_issued_before_it(
    app_client: TestClient, gateway: _StubAppTokenGateway, engine: sa.Engine
) -> None:
    token = gateway.issue("t1", iat=int(time.time()) - 60)
    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 200

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO federated_session_revocations (issuer, subject, session_id, jti, revoked_at, expires_at)"
                " VALUES (:iss, :sub, NULL, 'j1', CURRENT_TIMESTAMP, datetime('now', '+1 day'))"
            ),
            {"iss": _ISSUER, "sub": _SUBJECT},
        )

    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 401


def test_a_disabled_account_is_rejected(
    app_client: TestClient, gateway: _StubAppTokenGateway, engine: sa.Engine
) -> None:
    token = gateway.issue("t1")
    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 200

    with engine.begin() as connection:
        connection.execute(sa.text("UPDATE users SET is_active = 0 WHERE username = 'alice'"))

    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 401


def test_assetlinks_is_served_only_when_configured(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert app_client.get("/.well-known/assetlinks.json").status_code == 404

    monkeypatch.setenv("ANDROID_APP_PACKAGE", "com.nolumia.exampleapp")
    monkeypatch.setenv("ANDROID_APP_CERT_FINGERPRINTS", '["AA:BB"]')
    body = app_client.get("/.well-known/assetlinks.json").json()
    assert body[0]["target"] == {
        "namespace": "android_app",
        "package_name": "com.nolumia.exampleapp",
        "sha256_cert_fingerprints": ["AA:BB"],
    }
