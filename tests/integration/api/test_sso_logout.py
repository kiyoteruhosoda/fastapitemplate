"""サインアウトを IdP まで通す経路（RP-Initiated Logout 1.0）。

確かめたいのは 3 つ。

1. **既定では通さない。** 設定を足さない限り、振る舞いが変わらないこと。
2. 有効にしたときだけ IdP へ送り出し、名乗り（``client_id``）と戻り先を載せること。
3. **通せない場面を失敗にしないこと。** IdP が対応していない・discovery が引けない
   ときも、利用者はログイン画面へ着く。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
    EndSessionRequest,
)
from bounded_contexts.identity_federation.presentation import dependencies

_ISSUER = "https://idp.example.test"
_END_SESSION = f"{_ISSUER}/logout"
_APP_BASE = "https://app.example.test"


@dataclass
class _StubGateway:
    """``end_session_url`` だけを持つ IdP。返す値をテストごとに差し替える。"""

    #: ``None`` = この IdP は RP-Initiated Logout に対応していない
    end_session: str | None = _END_SESSION
    #: 真なら discovery が引けない状況を演じる
    unavailable: bool = False
    seen: list[EndSessionRequest] = field(default_factory=list)

    def authorization_url(self, request: AuthorizationRequest) -> str:  # pragma: no cover
        raise AssertionError("この試験では認可要求は出ない")

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:  # pragma: no cover
        raise AssertionError("この試験ではコード交換は出ない")

    def end_session_url(self, request: EndSessionRequest) -> str | None:
        if self.unavailable:
            raise IdentityProviderUnavailableError
        self.seen.append(request)
        if self.end_session is None:
            return None
        query = f"client_id={request.provider.client_id}"
        if request.post_logout_redirect_uri:
            query += f"&post_logout_redirect_uri={request.post_logout_redirect_uri}"
        return f"{self.end_session}?{query}"


@pytest.fixture
def gateway() -> _StubGateway:
    return _StubGateway()


class _MakeClient(Protocol):
    def __call__(self, *, rp_logout: bool | None = None) -> TestClient: ...


@pytest.fixture
def make_client(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> _MakeClient:
    """SSO を有効にしたアプリを作る。RP ログアウトの可否は呼び出し側が決める。"""

    def _make(*, rp_logout: bool | None = None) -> TestClient:
        from presentation.fastapi.app import create_app

        monkeypatch.setenv("APP_BASE_URL", _APP_BASE)
        monkeypatch.setenv("OIDC_ENABLED", "true")
        monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
        monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
        monkeypatch.setenv("OIDC_REDIRECT_URI", f"{_APP_BASE}/api/auth/sso/callback")
        if rp_logout is not None:
            monkeypatch.setenv("OIDC_RP_LOGOUT_ENABLED", "true" if rp_logout else "false")
        app: FastAPI = create_app()
        app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
        return TestClient(app)

    return _make


def _logout(client: TestClient) -> httpx.Response:
    return client.get("/api/auth/sso/logout", follow_redirects=False)


def test_the_default_does_not_reach_the_idp(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """設定を足さない限り振る舞いを変えない。**ここが既定であることが要件。**"""
    with make_client() as client:
        response = _logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert gateway.seen == []


def test_the_default_is_reported_to_the_screen(make_client: _MakeClient) -> None:
    with make_client() as client:
        assert client.get("/api/auth/sso/provider").json()["rp_logout_enabled"] is False


def test_enabling_it_sends_the_browser_to_the_idp(make_client: _MakeClient, gateway: _StubGateway) -> None:
    with make_client(rp_logout=True) as client:
        response = _logout(client)
        assert client.get("/api/auth/sso/provider").json()["rp_logout_enabled"] is True
    assert response.status_code == 303
    assert response.headers["location"].startswith(_END_SESSION)
    assert "client_id=rp" in response.headers["location"]


def test_the_landing_uri_defaults_to_the_app_base_url(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """設定を 1 つ増やさずに戻り先を決める。**2 か所に書くとずれる。**"""
    with make_client(rp_logout=True) as client:
        _logout(client)
    assert gateway.seen[0].post_logout_redirect_uri == f"{_APP_BASE}/api/auth/sso/signed-out"


def test_an_idp_without_the_endpoint_is_not_an_error(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """対応していない IdP でも、利用者はログイン画面に着く。"""
    gateway.end_session = None
    with make_client(rp_logout=True) as client:
        response = _logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_an_unreachable_idp_is_not_an_error(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """discovery が引けなくても断らない。アプリ側のセッションは既に終わっている。"""
    gateway.unavailable = True
    with make_client(rp_logout=True) as client:
        response = _logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_the_landing_route_returns_to_the_login_screen(make_client: _MakeClient) -> None:
    """IdP に登録するのはこの経路。**SPA のルーティングとは切り離しておく。**"""
    with make_client(rp_logout=True) as client:
        response = client.get("/api/auth/sso/signed-out", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?signed_out=1"
