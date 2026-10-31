"""パスワードで入る人に二要素認証を必須にする（ADR-0093）。"""

from __future__ import annotations

import httpx2
import pyotp
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.value_objects.federated_login import FederatedLogin
from bounded_contexts.identity_federation.domain.value_objects.federated_session import FederatedSession
from presentation.fastapi.dependencies.auth import REFRESH_COOKIE_PATH, REFRESH_TOKEN_COOKIE
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from presentation.fastapi.services.token_service import TokenService, create_machine_access_token
from presentation.fastapi.services.two_factor_requirement import needs_two_factor_setup
from shared.domain.auth import master_data
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow_aware

_ENROLLMENT = "/api/account/security/two-factor/enrollment"
_CONFIRMATION = "/api/account/security/two-factor/confirmation"
_REMOVAL = "/api/account/security/two-factor/removal"
_SETUP_REQUIRED = "two_factor_setup_required"


def _login(client: TestClient, **extra: object) -> httpx2.Response:
    return client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD, **extra},
    )


def _headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def _enroll(client: TestClient) -> str:
    enrollment = client.post(_ENROLLMENT, headers=_headers(client))
    assert enrollment.status_code == 200, enrollment.text
    secret = str(enrollment.json()["secret"])
    confirmation = client.post(_CONFIRMATION, headers=_headers(client), json={"code": pyotp.TOTP(secret).now()})
    assert confirmation.status_code == 200, confirmation.text
    return secret


def _refresh(client: TestClient) -> httpx2.Response:
    return client.post("/api/auth/refresh", headers=_headers(client))


def _admin(session: Session) -> User:
    return session.scalars(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)).one()


@pytest.fixture
def required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_TWO_FACTOR_REQUIRED", "true")


@pytest.mark.usefixtures("required")
def test_an_unenrolled_user_can_only_reach_the_enrollment(client: TestClient) -> None:
    assert _login(client).status_code == 200

    me = client.get("/api/auth/me").json()
    assert me[_SETUP_REQUIRED] is True
    assert me["scopes"] == []
    assert client.get("/api/account/security/two-factor").json()["required"] is True

    for method, path in (
        ("GET", "/api/items"),
        ("GET", "/api/admin/users"),
        ("GET", "/api/account/security/passkeys"),
        ("GET", "/api/notifications"),
    ):
        response = client.request(method, path)
        assert response.status_code == 403, path
        assert response.json()["detail"]["error"] == _SETUP_REQUIRED, path
    switched = client.post("/api/auth/switch-role", headers=_headers(client), json={"role": None})
    assert switched.status_code == 403


@pytest.mark.usefixtures("required")
def test_enrolling_and_refreshing_gives_the_permissions_back(client: TestClient) -> None:
    _login(client)
    _enroll(client)
    assert _refresh(client).status_code == 200

    me = client.get("/api/auth/me").json()
    assert me[_SETUP_REQUIRED] is False
    assert me["scopes"]
    assert client.get("/api/items").status_code == 200


@pytest.mark.usefixtures("required")
def test_an_enrolled_user_comes_in_as_before(client: TestClient) -> None:
    _login(client)
    secret = _enroll(client)
    client.cookies.clear()

    assert _login(client).status_code == 401  # コードを求める
    assert _login(client, totp_code=pyotp.TOTP(secret).now()).status_code == 200
    assert client.get("/api/auth/me").json()[_SETUP_REQUIRED] is False
    assert client.get("/api/items").status_code == 200


def test_nothing_changes_while_it_is_not_required(client: TestClient) -> None:
    assert _login(client).status_code == 200
    me = client.get("/api/auth/me").json()
    assert me[_SETUP_REQUIRED] is False
    assert me["scopes"]
    assert client.get("/api/account/security/two-factor").json()["required"] is False
    assert client.get("/api/items").status_code == 200


def test_it_reaches_a_running_session_at_the_next_refresh(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)
    assert client.get("/api/items").status_code == 200

    monkeypatch.setenv("LOCAL_TWO_FACTOR_REQUIRED", "true")
    assert _refresh(client).status_code == 200
    assert client.get("/api/items").status_code == 403


def test_turning_it_off_gives_the_permissions_back_at_the_next_refresh(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_TWO_FACTOR_REQUIRED", "true")
    _login(client)
    assert client.get("/api/items").status_code == 403

    monkeypatch.setenv("LOCAL_TWO_FACTOR_REQUIRED", "false")
    assert _refresh(client).status_code == 200
    assert client.get("/api/items").status_code == 200


def test_a_closed_local_entrance_does_not_require_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # 閉じていると登録の口も断るので、効かせると行き止まりになる
    monkeypatch.setenv("LOCAL_TWO_FACTOR_REQUIRED", "true")
    assert settings.local_two_factor_required is True
    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "false")
    assert settings.local_two_factor_required is False


@pytest.mark.usefixtures("required")
def test_two_factor_cannot_be_removed_while_it_is_required(client: TestClient) -> None:
    _login(client)
    secret = _enroll(client)
    _refresh(client)

    response = client.post(_REMOVAL, headers=_headers(client), json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "two_factor_required"


@pytest.mark.usefixtures("required")
def test_a_passkey_sign_in_is_not_asked_and_the_mark_survives_the_refresh(
    client: TestClient, db_session: Session
) -> None:
    user = _admin(db_session)
    assert needs_two_factor_setup(user, SessionCarryOver()) is True

    pair = TokenService.create_token_pair(user, carry=SessionCarryOver(signed_in_with_passkey=True))
    refresh_sessions.begin(
        db_session,
        session_id=str(pair["refresh_session_id"]),
        user_id=user.id,
        jti=str(pair["refresh_jti"]),
    )
    db_session.commit()
    client.cookies.set(REFRESH_TOKEN_COOKIE, str(pair["refresh_token"]), path=REFRESH_COOKIE_PATH)
    client.cookies.set(CSRF_COOKIE, "csrf")

    assert _refresh(client).status_code == 200
    assert client.get("/api/items").status_code == 200


@pytest.mark.usefixtures("required")
def test_a_federated_sign_in_is_not_asked(db_session: Session) -> None:
    login = FederatedLogin(session=FederatedSession(issuer="https://idp", subject="s"), started_at=utcnow_aware())
    assert needs_two_factor_setup(_admin(db_session), SessionCarryOver(federated_login=login)) is False


@pytest.mark.usefixtures("required")
def test_a_machine_token_is_not_asked(db_session: Session) -> None:
    token = create_machine_access_token(_admin(db_session), client_id="c", operations=frozenset({"item:view"}))
    principal, _ = TokenService.verify_access_token_with_reason(token.token)
    assert principal is not None
    assert principal.two_factor_setup_required is False
