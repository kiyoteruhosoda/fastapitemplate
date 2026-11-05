"""SSO で入ったログインはリフレッシュトークンを持たず、切れたら画面を出さずに続ける（ADR-0104）。

IdP との通信はゲートウェイを差し替えて止める。続ける往復は、画面が見えない枠で開く
``/api/auth/sso/renew`` から始まり、戻り（``/callback``）が Cookie を載せて結果の頁へ送る。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
    LogoutTokenVerification,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import FederatedLogin
from bounded_contexts.identity_federation.domain.value_objects.federated_session import FederatedSession
from bounded_contexts.identity_federation.presentation import dependencies
from presentation.fastapi.dependencies.auth import (
    ACCESS_TOKEN_COOKIE,
    LOGOUT_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from presentation.fastapi.middleware.security_headers import frame_sources
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from presentation.fastapi.services.token_service import RENEWAL_CARRY_SECONDS, TokenService
from shared.domain.auth import master_data
from shared.infrastructure.models import RefreshSession, User
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow, utcnow_aware
from tests.conftest import register_issuer

_ISSUER = "https://idp.example.test"
_AUTHORIZE = f"{_ISSUER}/authorize"
_SUBJECT = "idp-subject"
_RENEWED = "/api/auth/sso/renewed"


@dataclass
class _StubGateway:
    """ID トークンを、検証済みのクレームとして返すだけの IdP。送り出した要求を覚える。"""

    requests: list[AuthorizationRequest] = field(default_factory=list)

    def authorization_url(self, request: AuthorizationRequest) -> str:
        self.requests.append(request)
        return f"{_AUTHORIZE}?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        return {
            "sub": _SUBJECT,
            "email": master_data.DEFAULT_ADMIN_EMAIL,
            "email_verified": True,
            "name": "Admin",
            "sid": "session-1",
        }

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:  # pragma: no cover
        raise NotImplementedError


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
    monkeypatch.setenv("OIDC_LINK_BY_EMAIL", "true")
    app: FastAPI = create_app()
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: gateway
    with TestClient(app) as client:
        yield client


def _state_of(location: str) -> str:
    return parse_qs(urlsplit(location).query)["state"][0]


def _sign_in_with_sso(client: TestClient) -> Any:
    """SSO で入る（認可要求 → 戻り → 券の引き換え）。券を換えた応答を返す。"""
    redirect = client.get("/api/auth/sso/login", follow_redirects=False)
    callback = client.get(
        f"/api/auth/sso/callback?code=c&state={_state_of(redirect.headers['location'])}",
        follow_redirects=False,
    )
    ticket = callback.headers["location"].split("ticket=")[1]
    exchanged = client.post("/api/auth/sso/token", json={"ticket": ticket})
    assert exchanged.status_code == 200
    return exchanged


def _renew(client: TestClient, query: str = "code=c") -> Any:
    """続ける往復（枠の中で開く口 → IdP → 戻り）。戻りの応答を返す。"""
    start = client.get("/api/auth/sso/renew", follow_redirects=False)
    assert start.status_code == 303
    return client.get(
        f"/api/auth/sso/callback?{query}&state={_state_of(start.headers['location'])}",
        follow_redirects=False,
    )


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=["HS256"],
        audience=settings.access_token_audience,
        issuer=settings.access_token_issuer,
        options={"verify_exp": False},
    )


def _replace_access_cookie(client: TestClient, claims: dict[str, Any]) -> None:
    """手元のアクセストークンの Cookie を、書き換えたクレームのものに差し替える。"""
    for cookie in list(client.cookies.jar):
        if cookie.name == ACCESS_TOKEN_COOKIE:
            client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    client.cookies.set(ACCESS_TOKEN_COOKIE, jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256"))


def _set_cookie_headers(response: Any) -> list[str]:
    return [value for name, value in response.headers.multi_items() if name.lower() == "set-cookie"]


def test_an_sso_login_hands_out_no_refresh_token(sso_client: TestClient) -> None:
    """AC3: SSO で入ったログインに、リフレッシュトークンとログアウトの札の Cookie を出さない。"""
    exchanged = _sign_in_with_sso(sso_client)
    issued = " ".join(_set_cookie_headers(exchanged))
    assert f"{ACCESS_TOKEN_COOKIE}=" in issued
    assert f'{REFRESH_TOKEN_COOKIE}=""' in issued  # 前の仕組みの札は落とす
    assert REFRESH_TOKEN_COOKIE not in sso_client.cookies
    assert LOGOUT_TOKEN_COOKIE not in sso_client.cookies
    assert "rsid" not in _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])


def test_an_sso_login_keeps_no_refresh_record(sso_client: TestClient, engine: sa.Engine) -> None:
    _sign_in_with_sso(sso_client)
    with Session(engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(RefreshSession)) == 0


def test_the_access_cookie_outlives_the_token_to_carry_the_session(sso_client: TestClient) -> None:
    """トークンは 5 分で切れるが、Cookie は続ける往復のために残す。"""
    exchanged = _sign_in_with_sso(sso_client)
    access = next(value for value in _set_cookie_headers(exchanged) if value.startswith(f"{ACCESS_TOKEN_COOKIE}="))
    assert f"Max-Age={RENEWAL_CARRY_SECONDS}" in access
    claims = _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])
    assert claims["exp"] - claims["iat"] == settings.access_token_expires_seconds


def test_a_refresh_token_from_an_sso_login_is_refused(sso_client: TestClient, engine: sa.Engine) -> None:
    """この仕組みより前に出した札が残っていても、更新の口は通さず、控えと札を消す。"""
    with Session(engine) as db:
        user = db.scalars(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)).one()
        login = FederatedLogin(
            session=FederatedSession(issuer=_ISSUER, subject=_SUBJECT, session_id="s"), started_at=utcnow()
        )
        lifetime = refresh_sessions.lifetime_for(db, None)
        pair = TokenService.create_token_pair(
            user, carry=SessionCarryOver(federated_login=login), refresh_expires_at=lifetime.expires_at
        )
        issued = refresh_sessions.IssuedRefreshToken(
            session_id=str(pair["refresh_session_id"]), jti=str(pair["refresh_jti"]), lifetime=lifetime
        )
        refresh_sessions.begin(db, issued=issued, user_id=user.id)
        db.commit()
    sso_client.cookies.set(REFRESH_TOKEN_COOKIE, str(pair["refresh_token"]), path="/api/auth/refresh")
    sso_client.cookies.set(CSRF_COOKIE, "t")

    refused = sso_client.post("/api/auth/refresh", headers={CSRF_HEADER: "t"})

    assert refused.status_code == 401
    assert refused.json() == {"detail": {"error": "invalid_token"}}
    assert any(value.startswith(f'{REFRESH_TOKEN_COOKIE}=""') for value in _set_cookie_headers(refused))
    with Session(engine) as db:
        assert db.get(RefreshSession, str(pair["refresh_session_id"])) is None


def test_renewing_asks_the_idp_without_a_screen(sso_client: TestClient, gateway: _StubGateway) -> None:
    start = sso_client.get("/api/auth/sso/renew", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"].startswith(_AUTHORIZE)
    assert gateway.requests[-1].silent is True
    # 枠の中で開くので、自分のオリジンの枠にだけ入れてよい
    assert start.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in start.headers["content-security-policy"]


def test_renewing_carries_the_role_and_the_sign_in_time(sso_client: TestClient) -> None:
    """続けるのは入り直しではない。サインインした時刻とロールを引き継ぐ。"""
    _sign_in_with_sso(sso_client)
    switched = sso_client.post(
        "/api/auth/switch-role", json={"role": "owner"}, headers={CSRF_HEADER: sso_client.cookies[CSRF_COOKIE]}
    )
    assert switched.status_code == 200
    before = _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])

    renewed = _renew(sso_client)

    assert renewed.status_code == 303
    assert renewed.headers["location"] == f"{_RENEWED}?result=renewed"
    assert renewed.headers["x-frame-options"] == "SAMEORIGIN"
    after = _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])
    assert after["active_role"] == "owner"
    assert after["auth_time"] == before["auth_time"]
    assert REFRESH_TOKEN_COOKIE not in sso_client.cookies


def test_renewing_without_a_previous_token_signs_in_afresh(sso_client: TestClient) -> None:
    renewed = _renew(sso_client)
    assert renewed.headers["location"] == f"{_RENEWED}?result=renewed"
    assert _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])["active_role"] is None


def test_renewing_is_declined_when_the_idp_has_no_session(sso_client: TestClient) -> None:
    """AC2: IdP で入っていなければ ``declined``。画面はログイン画面へ送る。"""
    declined = _renew(sso_client, "error=login_required")
    assert declined.headers["location"] == f"{_RENEWED}?result=declined"
    assert ACCESS_TOKEN_COOKIE not in sso_client.cookies


def test_renewing_is_declined_when_someone_else_comes_back(sso_client: TestClient) -> None:
    """IdP で別の人に入り直していたら続けない。開いている画面は前の人のものだから。"""
    _sign_in_with_sso(sso_client)
    # 枠を開いた画面のトークンは別の人のもの（宛名だけを書き換えて作る）
    token = _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])
    token["sub"] = str(int(token["sub"]) + 1000)
    _replace_access_cookie(sso_client, token)
    declined = _renew(sso_client)
    assert declined.headers["location"] == f"{_RENEWED}?result=declined"


def test_a_broken_return_fails(sso_client: TestClient) -> None:
    failed = _renew(sso_client, "error=server_error")
    assert failed.headers["location"] == f"{_RENEWED}?result=failed"


def test_the_result_page_may_only_be_framed_by_this_origin(sso_client: TestClient) -> None:
    page = sso_client.get(f"{_RENEWED}?result=renewed")
    assert page.status_code == 200
    assert page.headers["x-frame-options"] == "SAMEORIGIN"
    assert page.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'self'"


def test_other_responses_still_refuse_every_frame(sso_client: TestClient) -> None:
    response = sso_client.get("/api/auth/sso/provider")
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    # 画面の枠に入れてよいのは自分と IdP の親ドメインの名前だけ
    assert "frame-src 'self' https://*.example.test" in csp


def test_an_expired_token_carries_the_session_only_within_the_window(sso_client: TestClient) -> None:
    _sign_in_with_sso(sso_client)
    claims = _claims(sso_client.cookies[ACCESS_TOKEN_COOKIE])
    stale = utcnow_aware() - timedelta(seconds=RENEWAL_CARRY_SECONDS + 60)
    claims["exp"] = int(stale.timestamp())
    claims["sub"] = str(int(claims["sub"]) + 1000)
    _replace_access_cookie(sso_client, claims)
    # 古すぎて読まない ——別の人のトークンでも、新しいログインとして入る（断らない）
    renewed = _renew(sso_client)
    assert renewed.headers["location"] == f"{_RENEWED}?result=renewed"


@pytest.mark.parametrize(
    ("issuer", "expected"),
    [
        ("https://identity.nolumia.com/01a0", "'self' https://*.nolumia.com"),
        ("http://localhost:8080/t", "'self' http://localhost:8080"),
        ("https://example.com", "'self' https://example.com"),
        ("", "'self'"),
        ("not a url", "'self'"),
    ],
)
def test_frame_sources_follow_the_issuer(issuer: str, expected: str) -> None:
    assert frame_sources(issuer) == expected
