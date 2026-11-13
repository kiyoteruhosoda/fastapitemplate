"""The SSO sign-in round trip (ADR-0077 §1).

Communication with the IdP is stopped by replacing the gateway. What we want to confirm is that
**the round-trip state travels in a signed cookie**, and that the return cannot complete without it.
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
from presentation.fastapi.dependencies.auth import ACCESS_TOKEN_COOKIE
from tests.conftest import register_issuer

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"


@dataclass
class _StubGateway:
    """An IdP that only builds the authorization URL and exchanges the code for fixed claims."""

    claims: dict[str, Any]
    seen: list[CodeExchange]

    def authorization_url(self, request: AuthorizationRequest) -> str:
        prompt = "&prompt=none" if request.silent else ""
        return f"{_AUTHORIZE}?state={request.state}&acr_values={' '.join(request.acr_values)}{prompt}"

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
    """An app with SSO enabled (configured to merge into existing users by verified email).

    ⚠ **Merging is not the default** (ADR-0077 §4). We want to see the round trip itself here, so it
    is explicitly enabled.
    """
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    monkeypatch.setenv("OIDC_LINK_BY_EMAIL", "true")
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
    """Nothing is stored in a table. The round-trip state travels in a signed cookie (ADR-0077 §1)."""
    _start(sso_client)
    assert transaction_cookie.COOKIE_NAME in sso_client.cookies


def test_a_callback_without_the_cookie_is_refused(sso_client: TestClient) -> None:
    """⚠ Login CSRF. Even if the victim is made to follow an authorization request started by the
    attacker, their browser has no matching cookie, so it cannot complete."""
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
    # The token travels in a cookie (ADR-0076 §4). The body carries only the lifetime and the return URL.
    assert exchanged.json()["expires_in"] > 0
    assert sso_client.cookies[ACCESS_TOKEN_COOKIE]

    # The ticket is single-use.
    assert sso_client.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 401


def test_a_silent_attempt_asks_the_idp_not_to_show_a_screen(sso_client: TestClient) -> None:
    """The attempt made when the sign-in screen opens (ADR-0077 §9) is sent with ``prompt=none``."""
    response = sso_client.get("/api/auth/sso/login?prompt=none", follow_redirects=False)
    assert response.status_code == 303
    assert "prompt=none" in response.headers["location"]
    # Not added to ordinary round trips
    assert "prompt=" not in sso_client.get("/api/auth/sso/login", follow_redirects=False).headers["location"]


@pytest.mark.parametrize(
    "error",
    ["login_required", "consent_required", "interaction_required", "account_selection_required", "access_denied"],
)
def test_a_declined_silent_attempt_returns_to_the_login_screen_without_an_error(
    sso_client: TestClient, error: str
) -> None:
    """Not signed in at the IdP. Not a failure, so no ``sso_error``; the destination is carried back."""
    response = sso_client.get("/api/auth/sso/login?prompt=none&redirect_to=/items", follow_redirects=False)
    state = response.headers["location"].split("state=")[1].split("&")[0]
    back = sso_client.get(f"/api/auth/sso/callback?error={error}&state={state}", follow_redirects=False)
    assert back.status_code == 303
    location = back.headers["location"]
    # The return goes to the entrance of the tenant that started the round trip (ADR-0079 §4)
    assert location.endswith("/login?sso_silent=declined&redirect_to=%2Fitems")
    assert "sso_error" not in location
    assert transaction_cookie.COOKIE_NAME not in sso_client.cookies


def test_a_declined_ordinary_attempt_is_still_an_error(sso_client: TestClient) -> None:
    """``login_required`` on a round trip started by the button is still returned as an error."""
    state = _start(sso_client)
    back = sso_client.get(f"/api/auth/sso/callback?error=login_required&state={state}", follow_redirects=False)
    assert "sso_error=login_required" in back.headers["location"]


def test_a_silent_attempt_that_succeeds_signs_in_as_usual(sso_client: TestClient) -> None:
    response = sso_client.get("/api/auth/sso/login?prompt=none", follow_redirects=False)
    state = response.headers["location"].split("state=")[1].split("&")[0]
    back = sso_client.get(f"/api/auth/sso/callback?code=the-code&state={state}", follow_redirects=False)
    assert back.headers["location"].startswith("/login/sso?ticket=")


def test_by_default_an_unknown_account_is_not_linked_to_a_local_one(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠ By default, do not silently merge into a local account with the same email address (ADR-0077 §4).

    The meaning of ``email_verified`` can differ between the IdP and the RP. In assay this value means
    "the tenant administrator claims so", not proof by the person.
    """
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    app = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        state = _start(client)
        response = client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
        assert "sso_error=sso_account_not_linked" in response.headers["location"]


def test_a_requested_acr_is_sent_and_verified(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If requested, verify it. If it does not come back, refuse (ADR-0076 §3 decision 1)."""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    monkeypatch.setenv("OIDC_ACR_VALUES", '["urn:assay:ac:mfa"]')
    app = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        redirect = client.get("/api/auth/sso/login", follow_redirects=False)
        # It is in the authorization request (the stub copies it into the URL as is).
        assert "acr_values=urn:assay:ac:mfa" in redirect.headers["location"]
        state = redirect.headers["location"].split("state=")[1].split("&")[0]
        # The ID token has no acr, so refuse. **Do not read what did not come back as satisfied.**
        response = client.get(
            f"/api/auth/sso/callback?code=c&state={state}",
            follow_redirects=False,
        )
        assert "sso_error=sso_acr_not_satisfied" in response.headers["location"]


def test_the_profile_copy_follows_the_idp(sso_client: TestClient, gateway: _StubGateway, engine: sa.Engine) -> None:
    """⚠ **The copy treats the IdP as the source of truth** (ADR-0077 §6 / idp ADR-0049 G4, I5).

    Without rewriting it, a rename or email change on the other side would leave **our display stale
    forever**.
    """
    from sqlalchemy.orm import sessionmaker

    from shared.infrastructure.models import User

    state = _start(sso_client)
    sso_client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)

    gateway.claims = {**gateway.claims, "name": "改名した人", "email": "renamed@example.com"}
    state = _start(sso_client)
    sso_client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        user = session.scalars(sa.select(User).where(User.email == "renamed@example.com")).one()
        assert user.username == "改名した人"


def test_a_name_another_user_already_has_is_not_copied(
    sso_client: TestClient, gateway: _StubGateway, engine: sa.Engine
) -> None:
    """⚠ **Updating the copy never breaks sign-in.** Only fields that clash on a unique column are skipped."""
    from sqlalchemy.orm import sessionmaker

    from shared.infrastructure.models import User

    state = _start(sso_client)
    sso_client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(User(email="taken@example.com", username="taken", is_active=True))
        session.commit()

    gateway.claims = {**gateway.claims, "email": "taken@example.com"}
    state = _start(sso_client)
    response = sso_client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
    # ⚠ Sign-in passes (only the clashing field is skipped).
    assert response.status_code == 303
    assert "sso_error" not in response.headers["location"]
