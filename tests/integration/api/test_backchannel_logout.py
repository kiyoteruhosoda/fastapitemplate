"""停止の伝播（IdP → RP）が効いているか（ADR-0036 / ADR-0041）。

IdP との通信はゲートウェイを差し替えて止める。ここで確かめたいのは、**届いた通知が
実際にセッションを終わらせること**と、終わらせる範囲を間違えないことである。

⚠ **効くのは「次の更新のとき」である**（ADR-0041）。アクセストークンの検証は DB を
引かないので、止まった直後でも**手元のアクセストークンは寿命まで通る**。止める判定は
更新の 1 点に集約してあり、**上限時間はアクセストークンの寿命**（既定 5 分）になる。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

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
from bounded_contexts.identity_federation.presentation import dependencies
from presentation.fastapi.dependencies.auth import ACCESS_TOKEN_COOKIE
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.domain.auth import master_data
from shared.kernel.settings.settings import settings

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"
_SUBJECT = "idp-subject"
_LOGOUT = "/api/auth/sso/backchannel-logout"


@dataclass
class _StubGateway:
    """ID トークンと ``logout_token`` を、検証済みのクレームとして返すだけの IdP。

    ``logout_token`` は「``<sid>|<jti>``」という綴りにする。**署名の検証は
    Infrastructure 層の責任**なので、ここではそこを模さない。
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
        token = verification.logout_token
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
    monkeypatch.setenv("OIDC_CLIENT_ID", "rp")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    # 既存の管理者へ寄せる（この試験の主題は結び付け方ではない）。
    monkeypatch.setenv("OIDC_LINK_BY_EMAIL", "true")
    app: FastAPI = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client


def _sign_in_with_sso(client: TestClient) -> None:
    """SSO で入る（認可要求 → 戻り → 券の引き換え）。"""
    redirect = client.get("/api/auth/sso/login", follow_redirects=False)
    state = redirect.headers["location"].split("state=")[1].split("&")[0]
    callback = client.get(f"/api/auth/sso/callback?code=c&state={state}", follow_redirects=False)
    ticket = callback.headers["location"].split("ticket=")[1]
    assert client.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 200


def _post_logout(client: TestClient, logout_token: str) -> int:
    """IdP のサーバーが叩く経路。**Cookie も CSRF トークンも持たない。**"""
    with TestClient(client.app) as idp:
        return idp.post(_LOGOUT, data={"logout_token": logout_token}).status_code


def _refresh(client: TestClient) -> int:
    response = client.post("/api/auth/refresh", headers={CSRF_HEADER: client.cookies[CSRF_COOKIE]})
    return response.status_code


def test_a_stop_from_the_idp_ends_the_session_at_the_next_refresh(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200

    assert _post_logout(sso_client, "session-1|delivery-1") == 200

    # ⚠ **手元のアクセストークンは寿命まで通る**（ADR-0041。検証は DB を引かない）。
    assert sso_client.cookies[ACCESS_TOKEN_COOKIE]
    assert sso_client.get("/api/auth/me").status_code == 200
    # 終わるのは更新のとき。ここから先は新しいアクセストークンが出ない。
    assert _refresh(sso_client) == 401


def test_the_access_token_outlives_the_stop_only_until_it_expires(sso_client: TestClient) -> None:
    """⚠ **これが引き受けた緩さである**（ADR-0041）。

    止まった利用者が通り続ける上限は、アクセストークンの寿命そのものになる。
    短くするほど上限が縮み、長くするほど停止が遅れて効く。
    """
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    # 止まっているのに、手元のアクセストークンはまだ通る。
    assert sso_client.get("/api/auth/me").status_code == 200
    # その「まだ」の上限が寿命である。
    assert settings.access_token_expires_seconds <= 300


def test_a_stopped_session_cannot_be_refreshed(sso_client: TestClient) -> None:
    """⚠ **止める判定はここだけである**（ADR-0041）。

    アクセストークンの検証は DB を引かないので、ここが抜けると停止はどこにも
    効かなくなる ——寿命による上限そのものが無くなる。
    """
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _refresh(sso_client) == 401


def test_a_stop_for_another_session_leaves_this_one_alone(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-2|delivery-1") == 200
    assert _refresh(sso_client) == 200


def test_a_stop_without_a_sid_ends_every_session_of_that_user(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "|delivery-1") == 200
    assert _refresh(sso_client) == 401


def test_signing_in_again_after_a_stop_works(sso_client: TestClient, gateway: _StubGateway) -> None:
    """止めるのは**そのときのセッション**であって、利用者ではない。"""
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "|delivery-1") == 200
    gateway.sid = "session-2"
    _sign_in_with_sso(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200


def test_switching_roles_keeps_the_session_stoppable(sso_client: TestClient) -> None:
    """⚠ 出し直したトークンが宛名を落とすと、切り替えた瞬間に伝播から外れる。"""
    _sign_in_with_sso(sso_client)
    switched = sso_client.post(
        "/api/auth/switch-role",
        json={"role": None},
        headers={CSRF_HEADER: sso_client.cookies[CSRF_COOKIE]},
    )
    assert switched.status_code == 200, switched.text
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _refresh(sso_client) == 401


def test_a_resent_notice_is_accepted_but_changes_nothing(sso_client: TestClient, gateway: _StubGateway) -> None:
    """送り手は再送でも同じ ``jti`` を使う（idp の ADR-0024）。

    ⚠ **弾かないと、古い通知の再送で「いま生きているセッション」を落とせる**
    ——ここでは、同じ ``sid`` を使い回す IdP を想定して最悪の形にしてある。
    """
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    gateway.sid = "session-1"
    _sign_in_with_sso(sso_client)
    assert _post_logout(sso_client, "session-1|delivery-1") == 200
    assert _refresh(sso_client) == 200


def test_a_local_login_is_not_touched(sso_client: TestClient) -> None:
    """停止の伝播が消せるのは IdP 経由で始まったセッションだけ（ADR-0026）。"""
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
