"""Whether suspension propagation (IdP -> RP) works (ADR-0077 §3 / ADR-0076 §5).

Communication with the IdP is stopped by replacing the gateway. What we want to confirm is that
**a received notice actually ends the session**, and that it does not get the scope wrong.

⚠ **It takes effect "at the next refresh"** (ADR-0076 §5). Access-token verification does not
query the DB, so even right after suspension **the access token in hand stays valid until it
expires**. The suspension check is concentrated at the single refresh point, and **the upper bound
is the access-token lifetime** (5 minutes by default).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidLogoutTokenError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
    LogoutTokenVerification,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LOGOUT_EVENT,
)
from bounded_contexts.identity_federation.infrastructure import sql_session_revocation_repository
from bounded_contexts.identity_federation.presentation import dependencies
from presentation.fastapi.dependencies.auth import ACCESS_TOKEN_COOKIE
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.domain.auth import master_data
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow
from tests.conftest import register_issuer

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"
_SUBJECT = "idp-subject"
_LOGOUT = "/api/auth/sso/backchannel-logout"


@dataclass
class _StubGateway:
    """An IdP that just returns the ID token and ``logout_token`` as verified claims.

    ``logout_token`` is spelled "``<sid>|<jti>``". **Signature verification is the Infrastructure
    layer's responsibility**, so it is not imitated here.
    """

    sid: str = "session-1"
    rejected: set[str] = field(default_factory=set)

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{_AUTHORIZE}?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        return {
            "sub": _SUBJECT,
            "email": master_data.DEFAULT_ADMIN_EMAIL,
            "email_verified": True,
            "name": "Admin",
            "sid": self.sid,
        }

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:
        token = str(jwt.decode(verification.logout_token, options={"verify_signature": False})["raw"])
        if token in self.rejected:
            raise InvalidLogoutTokenError
        sid, _, jti = token.partition("|")
        claims: dict[str, Any] = {
            "iss": _ISSUER,
            "aud": verification.provider.client_id,
            "sub": _SUBJECT,
            "jti": jti,
            "events": {LOGOUT_EVENT: {}},
        }
        if sid:
            claims["sid"] = sid
        return claims


@pytest.fixture
def gateway() -> _StubGateway:
    return _StubGateway()


@pytest.fixture
def sso_client(
    engine: sa.Engine,
    gateway: _StubGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    # Merge into the existing administrator (how linking works is not the subject of this test).
    monkeypatch.setenv("OIDC_LINK_BY_EMAIL", "true")
    app: FastAPI = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client


def _sign_in_with_sso(client: TestClient) -> None:
    """Signs in via SSO (authorization request -> return -> ticket exchange)."""
    redirect = client.get("/api/auth/sso/login", follow_redirects=False)
    state = redirect.headers["location"].split("state=")[1].split("&")[0]
    callback = client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
    ticket = callback.headers["location"].split("ticket=")[1]
    assert client.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 200


def _post_logout(client: TestClient, logout_token: str) -> int:
    """The path the IdP server calls. **It has neither a cookie nor a CSRF token.**

    The notice is sent as a JWT (the issuer selects the tenant; ADR-0079 §4). The contents
    "``<sid>|<jti>``" go in ``raw`` and verification is handled by the stub IdP.
    """
    signed = jwt.encode({"iss": _ISSUER, "raw": logout_token}, "stub-idp-key", algorithm="HS256")
    with TestClient(client.app) as idp:
        return idp.post(_LOGOUT, data={"logout_token": signed}).status_code


def _reissue(client: TestClient) -> int:
    """Whether the reissue entrance passes. SSO sign-ins hold no refresh marker (ADR-0104), so whether
    they were stopped is seen at an entrance that reissues tokens (role switching). Querying the IdP
    (continuation) is refused on the IdP side."""
    response = client.post(
        "/api/auth/switch-role",
        json={"role": None},
        headers={CSRF_HEADER: client.cookies[CSRF_COOKIE]},
    )
    return response.status_code


def test_a_stop_from_the_idp_ends_the_session_at_the_next_refresh(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200

    assert _post_logout(sso_client, "session-1|delivery-1") == 200

    # ⚠ **The access token in hand stays valid until it expires** (ADR-0076 §5; verification does not query the DB).
    assert sso_client.cookies[ACCESS_TOKEN_COOKIE]
    assert sso_client.get("/api/auth/me").status_code == 200
    # It ends at refresh time. From here on no new access token is issued.
    assert _reissue(sso_client) == 401


def test_the_access_token_outlives_the_stop_only_until_it_expires(sso_client: TestClient) -> None:
    """⚠ **This is the accepted looseness** (ADR-0076 §5).

    How long a suspended user keeps getting through is bounded by the access-token lifetime itself.
    Shorter shrinks the bound; longer delays the suspension taking effect.
    """
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    # Suspended, yet the access token in hand still passes.
    assert sso_client.get("/api/auth/me").status_code == 200
    # The bound on that "still" is the lifetime.
    assert settings.access_token_expires_seconds <= 300


def test_a_stop_outlives_the_period_when_the_period_was_shortened(
    sso_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with a shorter period, revocation records are not deleted before existing sign-ins (ADR-0102)."""
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRES_SECONDS", "3600")
    _sign_in_with_sso(sso_client)
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRES_SECONDS", "60")
    assert _post_logout(sso_client, "session-1|delivery-1") == 200

    # Another suspension arrives after the current period (60 s) has passed. Cleanup runs at this point.
    later = utcnow() + timedelta(seconds=120)
    monkeypatch.setattr(sql_session_revocation_repository, "utcnow", lambda: later)
    assert _post_logout(sso_client, "another-session|delivery-2") == 200

    assert _reissue(sso_client) == 401


def test_a_stopped_session_cannot_be_refreshed(sso_client: TestClient) -> None:
    """⚠ **This is the only place the suspension is checked** (ADR-0076 §5).

    Access-token verification does not query the DB, so without this the suspension would take effect
    nowhere: the lifetime bound itself would disappear.
    """
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _reissue(sso_client) == 401


def test_a_stop_for_another_session_leaves_this_one_alone(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-2|delivery-1") == 200
    assert _reissue(sso_client) == 200


def test_a_stop_without_a_sid_ends_every_session_of_that_user(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "|delivery-1") == 200
    assert _reissue(sso_client) == 401


def test_signing_in_again_after_a_stop_works(sso_client: TestClient, gateway: _StubGateway) -> None:
    """What is stopped is **that session**, not the user."""
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "|delivery-1") == 200
    gateway.sid = "session-2"
    _sign_in_with_sso(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200


def _switch_role(client: TestClient) -> int:
    response = client.post(
        "/api/auth/switch-role",
        json={"role": None},
        headers={CSRF_HEADER: client.cookies[CSRF_COOKIE]},
    )
    return response.status_code


def test_switching_roles_keeps_the_session_stoppable(sso_client: TestClient) -> None:
    """⚠ If a reissued token dropped the subject, switching would immediately escape propagation."""
    _sign_in_with_sso(sso_client)
    assert _switch_role(sso_client) == 200
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _reissue(sso_client) == 401


def test_a_stopped_session_cannot_mint_new_tokens_by_switching_roles(sso_client: TestClient) -> None:
    """⚠ **Unless the reissue path is blocked, the lifetime bound is broken** (ADR-0076 §5).

    Access-token verification does not query the DB, so even a suspended user's token in hand is valid
    until it expires. If that token could switch roles, **a new token could be obtained every 5
    minutes**, staying signed in indefinitely.
    """
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    # Read paths still pass (the accepted looseness).
    assert sso_client.get("/api/auth/me").status_code == 200
    # ⚠ Reissue paths do not pass.
    assert _switch_role(sso_client) == 401


def test_a_stopped_session_cannot_register_a_new_way_in(sso_client: TestClient) -> None:
    """⚠ **A suspended user cannot create new ways in** (ADR-0076 §5 decision 6).

    Enrolling two-factor authentication or a passkey "adds a way in". Access-token verification does
    not query the DB, so a suspended user's token in hand is valid until it expires; letting that token
    add ways in would undo half the point of suspending.
    """
    _sign_in_with_sso(sso_client)
    assert sso_client.get("/api/account/security/two-factor").status_code == 200

    assert _post_logout(sso_client, "session-1|delivery-1") == 200

    # Read-only paths still pass (the accepted looseness).
    assert sso_client.get("/api/auth/me").status_code == 200
    # ⚠ Paths that recreate credentials do not pass.
    assert sso_client.get("/api/account/security/two-factor").status_code == 401


def test_a_resent_notice_is_accepted_but_changes_nothing(sso_client: TestClient, gateway: _StubGateway) -> None:
    """The sender uses the same ``jti`` for resends (idp ADR-0024).

    ⚠ **Without rejecting them, resending an old notice could kill "a session alive right now"**:
    the worst case is set up here, assuming an IdP that reuses the same ``sid``.
    """
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    gateway.sid = "session-1"
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _reissue(sso_client) == 200


def test_a_local_login_is_not_touched(sso_client: TestClient) -> None:
    """Suspension propagation can only end sessions that started via the IdP (ADR-0076 §3)."""
    signed_in = sso_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert _post_logout(sso_client, "|delivery-1") == 200
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_token_that_does_not_verify_is_refused(sso_client: TestClient, gateway: _StubGateway) -> None:
    gateway.rejected.add("forged")
    assert _post_logout(sso_client, "forged") == 400


def test_a_request_without_the_token_is_refused(sso_client: TestClient) -> None:
    with TestClient(sso_client.app) as idp:
        assert idp.post(_LOGOUT, data={"something_else": "x"}).status_code == 400
