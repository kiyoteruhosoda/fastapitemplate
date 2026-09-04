"""SSO ログインの往復（ADR-0025）。

IdP との通信はゲートウェイを差し替えて止める。ここで確かめたいのは**往復状態を
署名付き Cookie で運ぶこと**と、その Cookie が無ければ戻りを完了できないこと。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.presentation import dependencies, transaction_cookie

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"


@dataclass
class _StubGateway:
    """認可 URL を組み立て、コードを固定のクレームへ換えるだけの IdP。"""

    claims: dict[str, Any]
    seen: list[CodeExchange]

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{_AUTHORIZE}?state={request.state}&acr_values={' '.join(request.acr_values)}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        self.seen.append(exchange)
        return self.claims


@pytest.fixture
def gateway() -> _StubGateway:
    return _StubGateway(
        claims={
            "sub": "idp-subject",
            "email": "admin@example.com",
            "email_verified": True,
            "name": "Admin",
        },
        seen=[],
    )


@pytest.fixture
def sso_client(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """SSO を有効にしたアプリ（既存の利用者へ検証済みメールで寄せる構成）。"""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    app: FastAPI = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client


def _start(client: TestClient) -> str:
    response = client.get("/api/auth/sso/login", follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"].startswith(_AUTHORIZE)
    return response.headers["location"].split("state=")[1].split("&")[0]


def test_the_button_appears_once_sso_is_configured(sso_client: TestClient) -> None:
    body = sso_client.get("/api/auth/sso/provider").json()
    assert body["enabled"] is True


def test_the_round_trip_state_is_carried_in_a_cookie(sso_client: TestClient) -> None:
    """表に控えを置かない。往復状態は署名付き Cookie で運ぶ（ADR-0025）。"""
    _start(sso_client)
    assert transaction_cookie.COOKIE_NAME in sso_client.cookies


def test_a_callback_without_the_cookie_is_refused(sso_client: TestClient) -> None:
    """⚠ ログイン CSRF。攻撃者が始めた認可要求を踏まされても、被害者の
    ブラウザには対応する Cookie が無いので完了できない。"""
    state = _start(sso_client)
    sso_client.cookies.delete(transaction_cookie.COOKIE_NAME)
    response = sso_client.get(
        f"/api/auth/sso/callback?code=c&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "sso_error=sso_state_invalid" in response.headers["location"]


def test_a_mismatched_state_is_refused(sso_client: TestClient) -> None:
    _start(sso_client)
    response = sso_client.get("/api/auth/sso/callback?code=c&state=other", follow_redirects=False)
    assert response.status_code == 303
    assert "sso_error=sso_state_invalid" in response.headers["location"]


def test_a_successful_round_trip_hands_a_ticket_to_the_spa(sso_client: TestClient) -> None:
    state = _start(sso_client)
    response = sso_client.get(
        f"/api/auth/sso/callback?code=the-code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith("/login/sso?ticket=")
    ticket = location.split("ticket=")[1]

    exchanged = sso_client.post("/api/auth/sso/token", json={"ticket": ticket})
    assert exchanged.status_code == 200, exchanged.text
    assert exchanged.json()["token_type"] == "bearer"

    # 券は 1 回限り。
    assert sso_client.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 401


def test_a_requested_acr_is_sent_and_verified(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """要求したら確かめる。返ってこなければ断る（ADR-0026 決定 1）。"""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    monkeypatch.setenv("OIDC_ACR_VALUES", '["urn:assay:ac:mfa"]')
    app = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        redirect = client.get("/api/auth/sso/login", follow_redirects=False)
        # 認可要求に載っている（スタブがそのまま URL へ写している）。
        assert "acr_values=urn:assay:ac:mfa" in redirect.headers["location"]
        state = redirect.headers["location"].split("state=")[1].split("&")[0]
        # ID トークンに acr が無いので断る。**返ってこないものを満たしたと読まない。**
        response = client.get(
            f"/api/auth/sso/callback?code=c&state={state}",
            follow_redirects=False,
        )
        assert "sso_error=sso_acr_not_satisfied" in response.headers["location"]
