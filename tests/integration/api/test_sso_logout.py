"""Carrying sign-out through to the IdP (RP-Initiated Logout 1.0).

Three things are checked.

1. **Off by default.** Behaviour does not change unless the setting is added.
2. Only when enabled, send the user to the IdP with the identity (``client_id``) and the return URL.
3. **Situations where it cannot be carried through are not failures.** Even when the IdP does not
   support it or discovery cannot be fetched, the user lands on the sign-in screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx2
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
from shared.domain.auth import master_data
from tests.conftest import register_issuer

_ISSUER = "https://idp.example.test"
_END_SESSION = f"{_ISSUER}/logout"
_APP_BASE = "https://app.example.test"


@dataclass
class _StubGateway:
    """An IdP that has only ``end_session_url``. Each test replaces the returned value."""

    #: ``None`` = this IdP does not support RP-Initiated Logout
    end_session: str | None = _END_SESSION
    #: If true, simulate discovery being unreachable
    unavailable: bool = False
    seen: list[EndSessionRequest] = field(default_factory=list)

    def authorization_url(self, request: AuthorizationRequest) -> str:  # pragma: no cover
        raise AssertionError("No authorization request is made in this test")

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:  # pragma: no cover
        raise AssertionError("No code exchange is made in this test")

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
    """Creates an app with SSO enabled. The caller decides whether RP logout is available."""

    def _make(*, rp_logout: bool | None = None) -> TestClient:
        from presentation.fastapi.app import create_app

        monkeypatch.setenv("APP_BASE_URL", _APP_BASE)
        monkeypatch.setenv("OIDC_ENABLED", "true")
        monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
        register_issuer(_ISSUER)
        monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
        monkeypatch.setenv("OIDC_REDIRECT_URI", f"{_APP_BASE}/api/auth/sso/callback")
        if rp_logout is not None:
            monkeypatch.setenv("OIDC_RP_LOGOUT_ENABLED", "true" if rp_logout else "false")
        app: FastAPI = create_app()
        app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
        return TestClient(app)

    return _make


def _logout(client: TestClient, *, site: str | None = "same-origin") -> httpx2.Response:
    headers = {} if site is None else {"Sec-Fetch-Site": site}
    return client.get("/api/auth/sso/logout", follow_redirects=False, headers=headers)


def test_the_default_does_not_reach_the_idp(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """Behaviour does not change unless the setting is added. **That this is the default is the requirement.**"""
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
    """Determines the return URL without adding a setting. **Writing it in two places makes them drift.**"""
    with make_client(rp_logout=True) as client:
        _logout(client)
    assert gateway.seen[0].post_logout_redirect_uri == f"{_APP_BASE}/api/auth/sso/signed-out"


def test_an_idp_without_the_endpoint_is_not_an_error(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """Even with an IdP that does not support it, the user lands on the sign-in screen."""
    gateway.end_session = None
    with make_client(rp_logout=True) as client:
        response = _logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_an_unreachable_idp_is_not_an_error(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """Not refused even if discovery cannot be fetched. The app-side session has already ended."""
    gateway.unavailable = True
    with make_client(rp_logout=True) as client:
        response = _logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_the_landing_route_returns_to_the_login_screen(make_client: _MakeClient) -> None:
    """This is the path registered with the IdP. **Keep it separate from SPA routing.**"""
    with make_client(rp_logout=True) as client:
        response = client.get("/api/auth/sso/signed-out", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?signed_out=1"


def test_a_cross_site_request_cannot_end_the_sso_session(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """A navigation triggered from another site does not go through to the IdP.

    ⚠ **This entrance changes state without authentication.** And what it changes is the IdP session
    shared by every app. Unprotected, placing ``<img src="…/logout">`` anywhere would lock users out
    from other apps too. **The IdP confirmation screen cannot be relied on** (assay does not show one).
    """
    with make_client(rp_logout=True) as client:
        response = _logout(client, site="cross-site")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert gateway.seen == []


def test_a_same_site_request_cannot_end_the_sso_session(make_client: _MakeClient, gateway: _StubGateway) -> None:
    """Not from sibling subdomains either. Only from our own origin."""
    with make_client(rp_logout=True) as client:
        response = _logout(client, site="same-site")
    assert response.headers["location"] == "/login"
    assert gateway.seen == []


def test_the_user_typing_the_url_is_allowed(make_client: _MakeClient) -> None:
    """Allowed from the address bar or bookmarks (``none``), a value other sites cannot produce."""
    with make_client(rp_logout=True) as client:
        response = _logout(client, site="none")
    assert response.headers["location"].startswith(_END_SESSION)


def test_a_browser_without_the_header_is_allowed(make_client: _MakeClient) -> None:
    """Do not lock out old browsers that do not send the header.

    What we want to block is **navigation triggered from another site**, where current browsers always
    send it. Closing it when absent too would do more harm by making sign-out impossible on old setups.
    """
    with make_client(rp_logout=True) as client:
        response = _logout(client, site=None)
    assert response.headers["location"].startswith(_END_SESSION)


def test_the_screen_learns_the_setting_from_me(make_client: _MakeClient) -> None:
    """The decision is delivered on ``/me``. **No extra request on every sign-out.**

    ``/provider`` returns it too, but that is for the sign-in screen. If a signed-in screen fetched
    it, the sign-out path would gain one more round trip.
    """
    with make_client(rp_logout=True) as client:
        client.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD}
        )
        body = client.get("/api/auth/me").json()
    assert body["rp_logout_enabled"] is True


def test_me_reports_the_default_as_false(make_client: _MakeClient) -> None:
    with make_client() as client:
        client.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": master_data.DEFAULT_ADMIN_PASSWORD}
        )
        body = client.get("/api/auth/me").json()
    assert body["rp_logout_enabled"] is False
