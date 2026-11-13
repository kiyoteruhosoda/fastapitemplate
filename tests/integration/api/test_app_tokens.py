"""Calling the app entrances with the app's assay access token (the app signs in to assay directly; ADR-0081 §1)."""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.identity_federation.domain.exceptions import AppAccessTokenRejectedError
from bounded_contexts.identity_federation.presentation.app_bearer import app_token_gateway
from tests.conftest import register_issuer
from tests.dpop_device_key import DeviceKey

_ISSUER = "https://idp.example.test/tenant"
_APP = "exampleapp"
_SUBJECT = "01a0-alice"
_BASE_URL = "https://app.example.test"
_ME = f"{_BASE_URL}/api/app/me"


class _StubAppTokenGateway:
    """Treats the token string itself as the name of "which claims" it carries."""

    def __init__(self) -> None:
        self.tokens: dict[str, dict[str, Any]] = {}
        self.userinfo_calls = 0
        self.id_token_calls = 0

    def issue(self, name: str, **overrides: Any) -> str:
        """Shaped as a JWT like assay access tokens (the issuer selects the tenant; ADR-0079 §4).

        This IdP does the signature check, so any key will do.
        """
        claims = {"iss": _ISSUER, "sub": _SUBJECT, "client_id": _APP, "iat": int(time.time()), **overrides}
        token = jwt.encode({"iss": claims["iss"], "name": name}, "stub-idp-key", algorithm="HS256")
        self.tokens[token] = claims
        return token

    def verify_access_token(self, issuer: str, token: str) -> Mapping[str, Any]:
        assert issuer == _ISSUER
        if token not in self.tokens:
            raise AppAccessTokenRejectedError
        return self.tokens[token]

    def verify_id_token(self, issuer: str, id_token: str, client_ids: frozenset[str]) -> Mapping[str, Any]:
        assert issuer == _ISSUER
        self.id_token_calls += 1
        if id_token != "id-token-of-alice" or _APP not in client_ids:
            raise AppAccessTokenRejectedError
        return {"sub": _SUBJECT, "email": "alice@example.com", "email_verified": True, "name": "alice"}

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
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_AUTO_PROVISION", "true")
    monkeypatch.setenv("OIDC_DEFAULT_ROLES", '["member"]')
    monkeypatch.setenv("APP_CLIENT_IDS", f'["{_APP}"]')
    monkeypatch.setenv("APP_BASE_URL", _BASE_URL)
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

    # From the second time it is looked up by the link (userinfo is not fetched again)
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


# ---------------------------------------------------------------------------
# Tokens bound to the device key (DPoP; ADR-0103)
# ---------------------------------------------------------------------------


def _dpop(token: str, proof: str | None, *, id_token: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"DPoP {token}"}
    if proof is not None:
        headers["DPoP"] = proof
    if id_token is not None:
        headers["X-ID-Token"] = id_token
    return headers


def test_a_bound_token_is_accepted_with_a_proof_of_its_key(
    app_client: TestClient, gateway: _StubAppTokenGateway
) -> None:
    device = DeviceKey()
    token = gateway.issue("t1", cnf={"jkt": device.thumbprint})

    first = app_client.get(
        "/api/app/me", headers=_dpop(token, device.proof("GET", _ME, token), id_token="id-token-of-alice")
    )
    assert first.status_code == 200, first.text
    assert first.json()["email"] == "alice@example.com"
    # A first-time person's profile comes from the ID token (userinfo cannot be fetched with a bound token)
    assert gateway.userinfo_calls == 0
    assert gateway.id_token_calls == 1

    assert app_client.get("/api/app/me", headers=_dpop(token, device.proof("GET", _ME, token))).status_code == 200


def test_a_bound_token_alone_is_useless(app_client: TestClient, gateway: _StubAppTokenGateway) -> None:
    """Copying only the token to another device does not work (AC1)."""
    device, thief = DeviceKey(), DeviceKey()
    token = gateway.issue("t1", cnf={"jkt": device.thumbprint})
    first = _dpop(token, device.proof("GET", _ME, token), id_token="id-token-of-alice")
    assert app_client.get("/api/app/me", headers=first).status_code == 200

    # Presented as Bearer
    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 401
    # Presented as DPoP but without a proof
    missing = app_client.get("/api/app/me", headers=_dpop(token, None))
    assert missing.status_code == 401
    assert missing.json()["detail"]["error"] == "invalid_dpop_proof"
    assert missing.headers["WWW-Authenticate"].startswith("DPoP ")
    # Proof made with a different key
    stolen = app_client.get("/api/app/me", headers=_dpop(token, thief.proof("GET", _ME, token)))
    assert stolen.status_code == 401
    assert stolen.json()["detail"]["error"] == "invalid_dpop_proof"


def test_a_proof_is_used_only_once_and_only_for_its_request(
    app_client: TestClient, gateway: _StubAppTokenGateway
) -> None:
    device = DeviceKey()
    token = gateway.issue("t1", cnf={"jkt": device.thumbprint})
    proof = device.proof("GET", _ME, token)
    assert app_client.get("/api/app/me", headers=_dpop(token, proof, id_token="id-token-of-alice")).status_code == 200

    assert app_client.get("/api/app/me", headers=_dpop(token, proof)).status_code == 401
    # Proof for a different entrance or method
    other_path = device.proof("GET", f"{_BASE_URL}/api/notifications", token)
    assert app_client.get("/api/app/me", headers=_dpop(token, other_path)).status_code == 401
    other_method = device.proof("POST", _ME, token)
    assert app_client.get("/api/app/me", headers=_dpop(token, other_method)).status_code == 401


def test_an_unbound_token_is_not_taken_with_the_dpop_scheme(
    app_client: TestClient, gateway: _StubAppTokenGateway
) -> None:
    device = DeviceKey()
    token = gateway.issue("t1")
    assert app_client.get("/api/app/me", headers=_dpop(token, device.proof("GET", _ME, token))).status_code == 401
    # Existing apps (Bearer) are unchanged (AC3)
    assert app_client.get("/api/app/me", headers=_bearer(token)).status_code == 200
