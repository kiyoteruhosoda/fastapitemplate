"""本人の操作で IdP の口座と結び付ける導線（ADR-0040）。

ログインの往復（``test_sso_login``）と同じ経路で戻ってくるが、後始末が違う。
ここで確かめるのは

- 始めるには**入っていること**が要る（未認証は 401）
- 戻りの結び付け先は**往復を始めた利用者**で、いまのセッションではない
- 外すと入れなくなる利用者は断る

の 3 つ。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.presentation import dependencies, transaction_cookie
from shared.domain.auth import master_data
from tests.conftest import sign_in

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
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    app = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    return app


@pytest.fixture
def signed_in(sso_app: Any) -> Iterator[tuple[TestClient, dict[str, str]]]:
    """管理者として入ったブラウザと、更新系に要る CSRF ヘッダー。"""
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
    # 管理者はパスワードを持っているので、外しても入り口が残る。
    assert body["can_unlink"] is True


def test_the_identity_is_not_linked_after_signing_out(
    signed_in: tuple[TestClient, dict[str, str]],
) -> None:
    """⚠ 往復の途中で入れ替わったブラウザで、誰かの口座へ結び付けない。"""
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
    """⚠ 横取りになるので断る。片方が先に結び付けた相手は、もう片方には渡らない。"""
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
    """⚠ パスワードもパスキーも無い利用者からは外させない（締め出しになる）。"""
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
    # 2 回目は「結び付いていない」。
    assert client.delete("/api/auth/sso/link", headers=headers).status_code == 404


_SECOND_EMAIL = "second@example.com"
_SECOND_PASSWORD = "Second-password-1"


def _open(engine: sa.Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _make_second_user(engine: sa.Engine) -> tuple[str, str]:
    """管理者とは別の利用者を 1 人作る。"""
    from werkzeug.security import generate_password_hash

    from shared.infrastructure.models import User

    with _open(engine) as session:
        session.add(
            User(
                email=_SECOND_EMAIL,
                username="second",
                is_active=True,
                password_hash=generate_password_hash(_SECOND_PASSWORD),
            )
        )
        session.commit()
    return _SECOND_EMAIL, _SECOND_PASSWORD


def _drop_password(engine: sa.Engine, email: str) -> None:
    """ローカルのパスワードを落とす（IdP でしか入れない利用者にする。ADR-0038）。"""
    from shared.infrastructure.models import User

    with _open(engine) as session:
        user = session.scalars(sa.select(User).where(User.email == email)).one()
        user.password_hash = None
        session.commit()
