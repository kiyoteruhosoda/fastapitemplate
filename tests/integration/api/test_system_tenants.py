"""テナントの外側の管理（ADR-0061・ADR-0065）。

システム管理者がテナントを登録・停止・削除し、最初のテナント管理者を指名する。指名された人は
招待のメールで自分のパスワードを決めるか、テナントの IdP で初めて入ったときに席を受け取る。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.email_sender import IEmailSender
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.presentation import dependencies
from presentation.fastapi.services.password_reset_service import PasswordResetService
from shared.infrastructure.models import Tenant, User

_ACME = {
    "slug": "acme",
    "display_name": "Acme",
    "first_admin": {"email": "boss@acme.example", "username": "boss"},
}


def _create(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/system/tenants", json={**_ACME, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_only_system_administrators_manage_tenants(client: TestClient, admin_headers: dict[str, str]) -> None:
    """テナント管理者（owner）はテナントの外側に入れない。"""
    assert client.get("/api/system/tenants").status_code == 403
    assert client.post("/api/system/tenants", json=_ACME, headers=admin_headers).status_code == 403
    assert client.get("/api/system/administrators").status_code == 403


def test_a_tenant_is_registered_with_a_designated_administrator(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    created = _create(client, system_admin_headers)
    assert created["tenant"]["slug"] == "acme"
    # 試験ではメールを止めてあるので送れない（送れたかは画面に出す）
    assert created["designation"]["invitation_sent"] is False

    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        assert seat.tenant_id == created["tenant"]["id"]
        assert seat.role_names == ("owner",)
        # ⚠ 指名した人はパスワードを決めない（中身を見ない約束。ADR-0065）
        assert seat.password_hash is None

    listed = {t["slug"]: t for t in client.get("/api/system/tenants").json()}
    assert listed["acme"]["member_count"] == 1
    assert "users" not in listed["acme"]


def test_slug_and_issuer_belong_to_one_tenant(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    _create(client, system_admin_headers, issuer="https://idp.example.test/acme", client_id="rp")
    again = client.post("/api/system/tenants", json=_ACME, headers=system_admin_headers)
    assert again.status_code == 409
    same_issuer = client.post(
        "/api/system/tenants",
        json={**_ACME, "slug": "acme2", "issuer": "https://idp.example.test/acme"},
        headers=system_admin_headers,
    )
    assert same_issuer.json()["detail"]["error"] == "issuer_already_registered"


@dataclass
class _Outbox(IEmailSender):
    sent: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def test_the_invitation_lets_the_designated_person_choose_a_password(
    client: TestClient,
    other_client: TestClient,
    system_admin_headers: dict[str, str],
    engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _create(client, system_admin_headers)
    monkeypatch.setenv("MAIL_ENABLED", "true")
    outbox = _Outbox()
    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        assert PasswordResetService(sender=outbox).invite(session, seat, place="Acme") is True
        session.commit()
    token = outbox.sent[0].body.split("token=")[1].split()[0]

    chosen = other_client.post("/api/auth/reset-password", json={"token": token, "new_password": "boss-password-1"})
    assert chosen.status_code == 200, chosen.text
    response = other_client.post(
        "/api/auth/login", json={"email": "boss@acme.example", "password": "boss-password-1", "tenant": "acme"}
    )
    assert response.status_code == 200, response.text
    assert "user:manage" in other_client.get("/api/auth/me").json()["scopes"]


def test_a_suspended_tenant_cannot_sign_in_and_only_then_can_be_deleted(
    client: TestClient, other_client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    default_id = next(t["id"] for t in client.get("/api/system/tenants").json() if t["slug"] == "default")

    assert client.delete(f"/api/system/tenants/{default_id}", headers=system_admin_headers).status_code == 409
    suspended = client.put(
        f"/api/system/tenants/{default_id}", json={"status": "suspended"}, headers=system_admin_headers
    )
    assert suspended.json()["status"] == "suspended"

    from shared.domain.auth import master_data

    refused = other_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "tenant_suspended"

    assert client.delete(f"/api/system/tenants/{default_id}", headers=system_admin_headers).status_code == 204
    with Session(engine) as session:
        assert session.get(Tenant, default_id) is None
        assert session.scalar(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)) is None


def test_system_administrators_are_added_by_invitation_and_never_all_removed(
    client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    added = client.post(
        "/api/system/administrators",
        json={"email": "second@ops.example", "username": "second"},
        headers=system_admin_headers,
    )
    assert added.status_code == 201, added.text
    listed = client.get("/api/system/administrators").json()
    assert {a["email"] for a in listed} >= {"second@ops.example"}
    me = client.get("/api/auth/me").json()["user_id"]

    assert client.delete(f"/api/system/administrators/{me}", headers=system_admin_headers).status_code == 403
    removed = client.delete(f"/api/system/administrators/{added.json()['user_id']}", headers=system_admin_headers)
    assert removed.status_code == 204


# --- 指名された席を IdP で受け取る（ADR-0065） ----------------------------------

_ISSUER = "https://idp.example.test/acme"


@dataclass
class _StubGateway:
    email: str

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{request.provider.issuer}/authorize?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        return {"sub": "boss-subject", "email": self.email, "email_verified": True, "name": "Boss"}


@pytest.fixture
def sso_app(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    # ⚠ 寄せる設定（OIDC_LINK_BY_EMAIL）は既定の「寄せない」のまま。席はそれとは別に受け取れる
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: _StubGateway("boss@acme.example")
    yield app
    app.dependency_overrides.clear()


def test_the_designated_seat_is_claimed_at_the_first_sso_sign_in(
    sso_app: FastAPI, client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    created = _create(client, system_admin_headers, issuer=_ISSUER, client_id="acme-rp")
    with TestClient(sso_app) as browser:
        started = browser.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
        state = started.headers["location"].split("state=")[1]
        done = browser.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False)
        ticket = done.headers["location"].split("ticket=")[1]
        assert browser.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 200
        me = browser.get("/api/auth/me").json()
    assert me["user_id"] == created["designation"]["user_id"]
    assert "owner" in me["roles"]


def test_a_seat_someone_already_uses_is_not_taken_over(
    sso_app: FastAPI, client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """入り口を持った利用者は「席」ではない。寄せる設定が無ければ断る（ADR-0037）。"""
    created = _create(client, system_admin_headers, issuer=_ISSUER, client_id="acme-rp")
    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        seat.password_hash = generate_password_hash("boss-password-1")
        session.commit()
    with TestClient(sso_app) as browser:
        started = browser.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
        state = started.headers["location"].split("state=")[1]
        done = browser.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert "sso_error=sso_account_not_linked" in done.headers["location"]
