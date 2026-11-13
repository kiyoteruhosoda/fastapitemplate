"""The flow where a user links their own IdP account (ADR-0077 §5).

It returns via the same route as the sign-in round trip (``test_sso_login``) but the follow-up
differs. Checked here:

- Starting requires **being signed in** (unauthenticated gets 401)
- The link target on return is **the user who started the round trip**, not the current session
- Users who could no longer sign in after unlinking are refused

"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.identity_federation.domain.entities.federated_identity import FederatedIdentity
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.presentation import dependencies, transaction_cookie
from shared.domain.auth import master_data
from shared.infrastructure.models import User
from tests.conftest import register_issuer, sign_in

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"


@dataclass
class _StubGateway:
    subject: str = "idp-subject"
    seen: list[CodeExchange] = field(default_factory=list)

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{_AUTHORIZE}?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        self.seen.append(exchange)
        return {"sub": self.subject, "email": "admin@example.com", "email_verified": True}


@pytest.fixture
def gateway() -> _StubGateway:
    return _StubGateway()


@pytest.fixture
def sso_app(engine: sa.Engine, gateway: _StubGateway, monkeypatch: pytest.MonkeyPatch) -> Any:
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    app = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    return app


@pytest.fixture
def signed_in(sso_app: Any) -> Iterator[tuple[TestClient, dict[str, str]]]:
    """A browser signed in as the administrator, and the CSRF header needed for writes."""
    with TestClient(sso_app) as client:
        headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
        yield client, headers


def _start_link(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/auth/sso/link/start", headers=headers)
    assert response.status_code == 200, response.text
    url = str(response.json()["authorization_url"])
    assert url.startswith(_AUTHORIZE)
    return url.split("state=")[1].split("&")[0]


def test_starting_a_link_requires_being_signed_in(sso_app: Any) -> None:
    with TestClient(sso_app) as client:
        assert client.post("/api/auth/sso/link/start").status_code == 401


def test_the_round_trip_state_is_carried_in_a_cookie(signed_in: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = signed_in
    _start_link(client, headers)
    assert transaction_cookie.COOKIE_NAME in client.cookies


def test_a_completed_round_trip_links_the_identity(signed_in: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = signed_in
    assert client.get("/api/auth/sso/link", headers=headers).json()["linked"] is False

    state = _start_link(client, headers)
    response = client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/profile/security?sso_link=linked"

    body = client.get("/api/auth/sso/link", headers=headers).json()
    assert body["linked"] is True
    assert body["linked_at"].endswith("Z")
    # The administrator has a password, so a way in remains after unlinking.
    assert body["can_unlink"] is True


def test_the_identity_is_not_linked_after_signing_out(
    signed_in: tuple[TestClient, dict[str, str]],
) -> None:
    """⚠ Do not link someone's account in a browser that was swapped mid round trip."""
    client, headers = signed_in
    state = _start_link(client, headers)
    assert client.post("/api/auth/logout", headers=headers).status_code == 200

    response = client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/profile/security?sso_link_error=sso_link_session_mismatch"


def test_an_identity_that_belongs_to_someone_else_is_refused(
    sso_app: Any,
    engine: sa.Engine,
) -> None:
    """⚠ That would be a takeover, so refuse. An account already linked by one side does not go to the other."""
    with TestClient(sso_app) as first:
        headers = sign_in(first, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
        state = _start_link(first, headers)
        first.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)

    created = _make_second_user(engine)
    with TestClient(sso_app) as second:
        headers = sign_in(second, created[0], created[1])
        state = _start_link(second, headers)
        response = second.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
        assert response.headers["location"] == "/profile/security?sso_link_error=sso_identity_taken"


def test_the_last_entrance_is_not_removed(sso_app: Any, engine: sa.Engine) -> None:
    """⚠ Users with neither a password nor a passkey cannot unlink (it would lock them out)."""
    email, password = _make_second_user(engine)
    with TestClient(sso_app) as client:
        headers = sign_in(client, email, password)
        state = _start_link(client, headers)
        client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
        _drop_password(engine, email)

        assert client.get("/api/auth/sso/link", headers=headers).json()["can_unlink"] is False
        refused = client.delete("/api/auth/sso/link", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["detail"]["error"] == "sso_last_entrance"


def test_a_link_can_be_removed_while_a_password_remains(
    signed_in: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = signed_in
    state = _start_link(client, headers)
    client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)

    assert client.delete("/api/auth/sso/link", headers=headers).status_code == 200
    assert client.get("/api/auth/sso/link", headers=headers).json()["linked"] is False
    # The second time it is "not linked".
    assert client.delete("/api/auth/sso/link", headers=headers).status_code == 404


_SECOND_EMAIL = "second@example.com"
_SECOND_PASSWORD = "Second-password-1"


def _open(engine: sa.Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _make_second_user(engine: sa.Engine) -> tuple[str, str]:
    """Creates one user separate from the administrator."""
    from werkzeug.security import generate_password_hash

    from shared.infrastructure.models import User
    from shared.infrastructure.tenant_directory import DEFAULT_TENANT_SLUG, tenant_of_slug

    with _open(engine) as session:
        second = User(
            email=_SECOND_EMAIL,
            username="second",
            is_active=True,
            password_hash=generate_password_hash(_SECOND_PASSWORD),
        )
        second.join(tenant_of_slug(session, DEFAULT_TENANT_SLUG) or 0)
        session.add(second)
        session.commit()
    return _SECOND_EMAIL, _SECOND_PASSWORD


def _drop_password(engine: sa.Engine, email: str) -> None:
    """Drops the local password (making a user who can only sign in via the IdP; ADR-0076 §6)."""
    from shared.infrastructure.models import User

    with _open(engine) as session:
        user = session.scalars(sa.select(User).where(User.email == email)).one()
        user.password_hash = None
        session.commit()


def _link_the_admin(db_session: Session) -> None:
    admin = db_session.scalars(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)).one()
    SqlFederatedIdentityRepository(db_session).link(
        FederatedIdentity(issuer="https://idp.example", subject="linked", user_id=admin.id)
    )
    db_session.commit()


def test_a_linked_user_cannot_change_the_name_and_email_here(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
) -> None:
    _link_the_admin(db_session)
    headers = admin_headers
    me = client.get("/api/auth/me").json()
    assert me["profile_managed_by_idp"] is True

    for body in (
        {"email": "changed@example.com", "username": me["username"]},
        {"email": me["email"], "username": "changed"},
    ):
        response = client.put("/api/auth/me", json=body, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "profile_managed_by_idp"

    same = {"email": me["email"], "username": me["username"]}
    assert client.put("/api/auth/me", json=same, headers=headers).status_code == 200
    after = client.get("/api/auth/me").json()
    assert (after["email"], after["username"]) == (me["email"], me["username"])


def test_a_local_user_can_still_change_the_name(client: TestClient, admin_headers: dict[str, str]) -> None:
    me = client.get("/api/auth/me").json()
    assert me["profile_managed_by_idp"] is False

    response = client.put("/api/auth/me", json={"email": me["email"], "username": "renamed"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "renamed"
