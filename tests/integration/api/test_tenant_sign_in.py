"""テナントごとの入口（ADR-0061 決定 8・ADR-0064）。

- パスワード: ``/t/<slug>/login`` はそのテナントの中で探す。名前の無い入口は、テナントに
  属さない人と、テナントが 1 つだけのときのそのテナント
- メールアドレスの一意はテナントの中だけ（別のテナントに同じ人が居てよい）
- SSO: 送り出す先も戻りを受ける先も、入口で選んだテナントの発行者とクライアント
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.presentation import dependencies
from shared.domain.auth import master_data
from shared.infrastructure.models import Role, Tenant, User
from shared.infrastructure.tenant_directory import DEFAULT_TENANT_SLUG, tenant_of_slug
from tests.conftest import register_issuer, sign_in

_SHARED_EMAIL = "same.person@example.com"
_PASSWORD = "same-person-password-1"
_DEFAULT_ISSUER = "https://idp.example.test/default"
_ACME_ISSUER = "https://idp.example.test/acme"


def _add_tenant(engine: sa.Engine, slug: str, *, issuer: str | None = None) -> int:
    with sessionmaker(bind=engine)() as session:
        tenant = Tenant(slug=slug, display_name=slug.title(), issuer=issuer, client_id="acme-rp" if issuer else None)
        session.add(tenant)
        session.commit()
        return tenant.id


def _add_member(engine: sa.Engine, tenant_id: int, username: str) -> int:
    with sessionmaker(bind=engine)() as session:
        user = User(
            email=_SHARED_EMAIL,
            username=username,
            password_hash=generate_password_hash(_PASSWORD),
            is_active=True,
        )
        user.roles = [session.scalars(sa.select(Role).where(Role.name == "member")).one()]
        user.join(tenant_id)
        session.add(user)
        session.commit()
        return user.id


def _login(client: TestClient, tenant: str | None) -> int:
    body = {"email": _SHARED_EMAIL, "password": _PASSWORD, "tenant": tenant}
    return client.post("/api/auth/login", json=body).status_code


def _me(client: TestClient) -> str:
    return str(client.get("/api/auth/me").json()["username"])


def test_the_same_email_can_live_in_two_tenants(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    acme = _add_tenant(engine, "acme")
    _add_member(engine, acme, "acme-person")
    created = client.post(
        "/api/admin/users",
        json={"email": _SHARED_EMAIL, "username": "default-person", "password": _PASSWORD, "roles": ["member"]},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    # 同じテナントの中ではぶつかる
    again = client.post(
        "/api/admin/users",
        json={"email": _SHARED_EMAIL, "username": "twice", "password": _PASSWORD, "roles": ["member"]},
        headers=admin_headers,
    )
    assert again.status_code == 409


def test_the_entrance_decides_which_tenant_to_sign_in_to(
    client: TestClient, other_client: TestClient, engine: sa.Engine
) -> None:
    with sessionmaker(bind=engine)() as session:
        default_id = tenant_of_slug(session, DEFAULT_TENANT_SLUG)
    assert default_id is not None
    _add_member(engine, default_id, "default-person")
    _add_member(engine, _add_tenant(engine, "acme"), "acme-person")

    assert _login(client, "acme") == 200
    assert _me(client) == "acme-person"
    assert _login(other_client, "default") == 200
    assert _me(other_client) == "default-person"


def test_the_plain_entrance_serves_only_outsiders_once_there_are_two_tenants(
    client: TestClient, engine: sa.Engine, system_admin_headers: dict[str, str]
) -> None:
    """テナントが 2 つ以上なら、名前の無い入口で入れるのはテナントに属さない人だけ。"""
    _add_member(engine, _add_tenant(engine, "acme"), "acme-person")
    assert _login(client, None) == 401
    unknown = {"email": master_data.DEFAULT_ADMIN_EMAIL, "password": "x", "tenant": "nowhere"}
    assert client.post("/api/auth/login", json=unknown).status_code == 401
    # システム管理者は名前の無い入口で入れる（フィクスチャがそこで入っている）
    assert system_admin_headers


def test_the_plain_entrance_still_works_with_a_single_tenant(client: TestClient) -> None:
    """テナントが 1 つだけなら、入口は今までどおり（ADR-0061 決定 8）。"""
    sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)


# --- SSO ---------------------------------------------------------------------


@dataclass
class _StubGateway:
    """送り出し先と、戻りを受けた連携先を控える IdP。"""

    exchanged_with: list[str]

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{request.provider.issuer}/authorize?state={request.state}&client_id={request.provider.client_id}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        self.exchanged_with.append(exchange.provider.issuer)
        return {"sub": "acme-subject", "email": "newcomer@acme.example", "email_verified": True, "name": "New"}


@pytest.fixture
def sso_client(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, _StubGateway]]:
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    monkeypatch.setenv("OIDC_AUTO_PROVISION", "true")
    monkeypatch.setenv("OIDC_DEFAULT_ROLES", "member")
    register_issuer(_DEFAULT_ISSUER)
    _add_tenant(engine, "acme", issuer=_ACME_ISSUER)
    _add_tenant(engine, "local-only")
    gateway = _StubGateway(exchanged_with=[])
    app: FastAPI = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client, gateway


def test_the_sso_button_belongs_to_the_chosen_tenant(sso_client: tuple[TestClient, _StubGateway]) -> None:
    client, _ = sso_client
    assert client.get("/api/auth/sso/provider", params={"tenant": "acme"}).json()["enabled"] is True
    # SSO を持たないテナント・テナントを選ばない入口（2 つ以上ある）では出さない
    assert client.get("/api/auth/sso/provider", params={"tenant": "local-only"}).json()["enabled"] is False
    assert client.get("/api/auth/sso/provider").json()["enabled"] is False


def test_a_round_trip_stays_with_the_tenant_it_started_in(
    sso_client: tuple[TestClient, _StubGateway], engine: sa.Engine
) -> None:
    client, gateway = sso_client
    started = client.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
    location = started.headers["location"]
    assert location.startswith(f"{_ACME_ISSUER}/authorize")
    assert "client_id=acme-rp" in location
    state = location.split("state=")[1].split("&")[0]

    # 戻りの URL でテナントを書き換えても、受けるのは送り出したテナント
    done = client.get(
        "/api/auth/sso/callback", params={"code": "c", "state": state, "tenant": "default"}, follow_redirects=False
    )
    assert done.status_code == 303, done.text
    assert gateway.exchanged_with == [_ACME_ISSUER]
    with sessionmaker(bind=engine)() as session:
        newcomer = session.scalars(sa.select(User).where(User.email == "newcomer@acme.example")).one()
        acme = session.scalars(sa.select(Tenant).where(Tenant.slug == "acme")).one()
        assert newcomer.tenant_id == acme.id


def test_a_failed_round_trip_returns_to_the_tenants_entrance(sso_client: tuple[TestClient, _StubGateway]) -> None:
    client, _ = sso_client
    client.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
    failed = client.get("/api/auth/sso/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert failed.headers["location"].startswith("/t/acme/login?sso_error=")


def test_a_declined_silent_attempt_returns_to_the_tenants_entrance(
    sso_client: tuple[TestClient, _StubGateway],
) -> None:
    """ボタンを押さずに入る試し（ADR-0066）も、断られたら始めたテナントの入口へエラー無しで戻す。

    共通の入口へ戻すと、テナントが 2 つ以上ある環境ではそのテナントの IdP の入口が出ない。
    """
    client, _ = sso_client
    started = client.get(
        "/api/auth/sso/login",
        params={"tenant": "acme", "prompt": "none", "redirect_to": "/items"},
        follow_redirects=False,
    )
    state = started.headers["location"].split("state=")[1].split("&")[0]
    back = client.get(
        "/api/auth/sso/callback", params={"error": "login_required", "state": state}, follow_redirects=False
    )
    assert back.headers["location"] == "/t/acme/login?sso_silent=declined&redirect_to=%2Fitems"
