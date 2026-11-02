"""リフレッシュトークンの寿命と、更新で延ばすかの設定（ADR-0101）。"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from presentation.fastapi.dependencies.auth import (
    LOGOUT_COOKIE_PATH,
    LOGOUT_TOKEN_COOKIE,
    REFRESH_COOKIE_PATH,
    REFRESH_TOKEN_COOKIE,
)
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from presentation.fastapi.services.refresh_sessions import REUSE_GRACE_SECONDS
from shared.domain.auth import master_data
from shared.infrastructure.models import RefreshSession
from shared.kernel.settings.settings import settings
from shared.kernel.settings.system_settings_defaults import MAX_REFRESH_TOKEN_EXPIRES_SECONDS
from shared.kernel.timestamps import utcnow
from tests.conftest import sign_in

_EMAIL = master_data.DEFAULT_ADMIN_EMAIL
_PASSWORD = master_data.DEFAULT_ADMIN_PASSWORD
_REFRESH = "/api/auth/refresh"
_UTCNOW = "presentation.fastapi.services.refresh_sessions.utcnow"
_SLIDING = "REFRESH_TOKEN_SLIDING_ENABLED"
_PERIOD = "REFRESH_TOKEN_EXPIRES_SECONDS"


@pytest.fixture
def fixed_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_SLIDING, "false")


def _headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def _refresh_cookie(client: TestClient) -> str:
    return client.cookies.get(REFRESH_TOKEN_COOKIE, path=REFRESH_COOKIE_PATH) or ""


def _logout_cookie(client: TestClient) -> str:
    return client.cookies.get(LOGOUT_TOKEN_COOKIE, path=LOGOUT_COOKIE_PATH) or ""


def _row(engine: sa.Engine) -> RefreshSession:
    with Session(engine) as session:
        return session.scalars(sa.select(RefreshSession).order_by(RefreshSession.created_at.desc())).first()  # type: ignore[return-value]


def _after_the_grace() -> datetime:
    return utcnow() + timedelta(seconds=REUSE_GRACE_SECONDS + 1)


def _refresh_after_the_grace(client: TestClient) -> object:
    """猶予を過ぎた更新。猶予の中では振り替わらない（ADR-0092）。"""
    with patch(_UTCNOW, return_value=_after_the_grace()):
        return client.post(_REFRESH, headers=_headers(client))


def _exp(token: str) -> datetime:
    claims = jwt.decode(token, options={"verify_signature": False})
    return datetime.fromtimestamp(claims["exp"], UTC).replace(tzinfo=None)


def _max_age(response: object, cookie: str) -> int:
    headers = response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
    line = next(h for h in headers if h.startswith(f"{cookie}="))
    found = re.search(r"Max-Age=(\d+)", line)
    assert found is not None
    return int(found.group(1))


def _expire_the_row(engine: sa.Engine) -> None:
    with Session(engine) as session:
        session.execute(sa.update(RefreshSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        session.commit()


def _set_the_expiry(engine: sa.Engine, expires_at: datetime) -> None:
    with Session(engine) as session:
        session.execute(sa.update(RefreshSession).values(expires_at=expires_at))
        session.commit()


# --- 既定（延長あり）


def test_extending_is_the_default() -> None:
    assert settings.refresh_token_sliding_enabled is True


def test_the_settings_screen_offers_both(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert items[_PERIOD]["value_type"] == "integer"
    assert items[_SLIDING]["value_type"] == "boolean"
    assert items[_SLIDING]["value"] is True
    assert items[_SLIDING]["stored"] is False


def test_extending_moves_the_expiry_on_each_rotation(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    # 控えが今から期間ぶん先へ動いたことを見たいので、ログインの期限を手前へ寄せておく
    earlier = utcnow().replace(microsecond=0) + timedelta(seconds=60)
    _set_the_expiry(engine, earlier)

    moment = _after_the_grace()
    with patch(_UTCNOW, return_value=moment):
        response = client.post(_REFRESH, headers=_headers(client))

    assert response.status_code == 200
    expected = (moment + timedelta(seconds=settings.refresh_token_expires_seconds)).replace(microsecond=0)
    assert _row(engine).expires_at == expected
    assert _exp(_refresh_cookie(client)) == expected
    assert _exp(_logout_cookie(client)) == expected
    assert _max_age(response, REFRESH_TOKEN_COOKIE) == settings.refresh_token_expires_seconds
    assert _max_age(response, LOGOUT_TOKEN_COOKIE) == settings.refresh_token_expires_seconds


def test_the_row_and_the_tokens_agree_from_the_sign_in(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    expires_at = _row(engine).expires_at
    assert expires_at.microsecond == 0
    assert _exp(_refresh_cookie(client)) == expires_at
    assert _exp(_logout_cookie(client)) == expires_at


# --- 延長なし


@pytest.mark.usefixtures("fixed_lifetime")
def test_without_extending_the_expiry_stays_and_the_token_still_rotates(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    expires_at = _row(engine).expires_at
    first = _refresh_cookie(client)

    response = _refresh_after_the_grace(client)

    assert response.status_code == 200  # type: ignore[attr-defined]
    assert _refresh_cookie(client) != first
    row = _row(engine)
    assert row.expires_at == expires_at
    assert row.previous_jti is not None


@pytest.mark.usefixtures("fixed_lifetime")
def test_without_extending_everything_shows_the_remaining_time(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    # 残りが目に見えて短い状態を作る
    expires_at = utcnow().replace(microsecond=0) + timedelta(hours=1)
    _set_the_expiry(engine, expires_at)

    response = client.post(_REFRESH, headers=_headers(client))
    assert response.headers.get_list("set-cookie")
    assert not any(h.startswith(f"{REFRESH_TOKEN_COOKIE}=") for h in response.headers.get_list("set-cookie"))

    moment = _after_the_grace()
    with patch(_UTCNOW, return_value=moment):
        rotated = client.post(_REFRESH, headers=_headers(client))

    assert _row(engine).expires_at == expires_at
    assert _exp(_refresh_cookie(client)) == expires_at
    assert _exp(_logout_cookie(client)) == expires_at
    remaining = int((expires_at - moment).total_seconds())
    assert _max_age(rotated, REFRESH_TOKEN_COOKIE) == remaining
    assert _max_age(rotated, LOGOUT_TOKEN_COOKIE) == remaining


@pytest.mark.usefixtures("fixed_lifetime")
def test_without_extending_the_update_does_not_write_the_expiry(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    statements: list[str] = []

    def remember(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", remember)
    try:
        _refresh_after_the_grace(client)
    finally:
        sa.event.remove(engine, "before_cursor_execute", remember)

    rotation = next(s for s in statements if s.startswith("UPDATE refresh_sessions"))
    assert "expires_at=" not in rotation.split("WHERE")[0]
    # MariaDB は SET を左から評価する（ADR-0091）
    assert rotation.index("previous_jti=") < rotation.index("current_jti=")


def test_extending_writes_the_expiry_after_the_token_columns(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    statements: list[str] = []

    def remember(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", remember)
    try:
        _refresh_after_the_grace(client)
    finally:
        sa.event.remove(engine, "before_cursor_execute", remember)

    rotation = next(s for s in statements if s.startswith("UPDATE refresh_sessions"))
    assert rotation.index("previous_jti=") < rotation.index("current_jti=") < rotation.index("expires_at=")


@pytest.mark.usefixtures("fixed_lifetime")
def test_past_the_expiry_the_refresh_is_refused(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    _expire_the_row(engine)
    assert client.post(_REFRESH, headers=_headers(client)).status_code == 401


@pytest.mark.usefixtures("fixed_lifetime")
def test_without_extending_a_used_token_is_still_detected(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    used = _refresh_cookie(client)
    assert _refresh_after_the_grace(client).status_code == 200  # type: ignore[attr-defined]

    client.cookies.delete(REFRESH_TOKEN_COOKIE)
    client.cookies.set(REFRESH_TOKEN_COOKIE, used, path=REFRESH_COOKIE_PATH)
    moment = utcnow() + timedelta(seconds=(REUSE_GRACE_SECONDS + 1) * 2)
    with patch(_UTCNOW, return_value=moment):
        assert client.post(_REFRESH, headers=_headers(client)).status_code == 401

    with Session(engine) as session:
        recorded = session.scalars(
            sa.select(AuditLogModel.event_type).where(
                AuditLogModel.event_type == AuditEventType.REFRESH_TOKEN_REUSED.value
            )
        ).all()
    assert len(recorded) == 1


@pytest.mark.usefixtures("fixed_lifetime")
def test_a_racing_refresh_does_not_sign_out_without_extending(client: TestClient) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    first = _refresh_cookie(client)
    assert client.post(_REFRESH, headers=_headers(client)).status_code == 200
    second = _refresh_cookie(client)
    assert second != first

    for token in (first, second, first):
        client.cookies.delete(REFRESH_TOKEN_COOKIE)
        client.cookies.set(REFRESH_TOKEN_COOKIE, token, path=REFRESH_COOKIE_PATH)
        assert client.post(_REFRESH, headers=_headers(client)).status_code == 200


# --- 控えを引き継ぐ経路


@pytest.mark.usefixtures("fixed_lifetime")
def test_switching_roles_does_not_extend(client: TestClient, engine: sa.Engine) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    expires_at = utcnow().replace(microsecond=0) + timedelta(hours=1)
    _set_the_expiry(engine, expires_at)

    response = client.post("/api/auth/switch-role", json={"role": None}, headers=headers)

    assert response.status_code == 200
    assert _row(engine).expires_at == expires_at
    assert _exp(_refresh_cookie(client)) == expires_at
    assert _max_age(response, REFRESH_TOKEN_COOKIE) <= 3600


@pytest.mark.usefixtures("fixed_lifetime")
def test_switching_roles_past_the_expiry_is_refused(client: TestClient, engine: sa.Engine) -> None:
    """アクセストークンは期限の後も生きる。切り替えで出し直せると、繰り返すだけで上限が無くなる。"""
    headers = sign_in(client, _EMAIL, _PASSWORD)
    _expire_the_row(engine)
    assert client.post("/api/auth/switch-role", json={"role": None}, headers=headers).status_code == 401


@pytest.mark.usefixtures("fixed_lifetime")
def test_changing_the_password_makes_a_new_row_with_the_same_expiry(client: TestClient, engine: sa.Engine) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    expires_at = utcnow().replace(microsecond=0) + timedelta(hours=1)
    _set_the_expiry(engine, expires_at)

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": _PASSWORD, "new_password": "A-new-passw0rd-for-the-test"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    with Session(engine) as session:
        rows = session.scalars(sa.select(RefreshSession)).all()
    assert len(rows) == 2
    assert {row.expires_at for row in rows} == {expires_at}
    assert _exp(_refresh_cookie(client)) == expires_at
    assert _max_age(response, REFRESH_TOKEN_COOKIE) <= 3600


def test_changing_the_password_starts_over_when_extending(client: TestClient, engine: sa.Engine) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    earlier = utcnow().replace(microsecond=0) + timedelta(hours=1)
    _set_the_expiry(engine, earlier)

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": _PASSWORD, "new_password": "A-new-passw0rd-for-the-test"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert _exp(_refresh_cookie(client)) > earlier


# --- 設定を変えたとき


def test_turning_it_off_does_not_shrink_and_keeps_the_sign_in(
    client: TestClient, engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    expires_at = _row(engine).expires_at

    monkeypatch.setenv(_SLIDING, "false")
    monkeypatch.setenv(_PERIOD, "60")

    assert _refresh_after_the_grace(client).status_code == 200  # type: ignore[attr-defined]
    assert _row(engine).expires_at == expires_at
    assert _exp(_refresh_cookie(client)) == expires_at


def test_turning_it_back_on_extends_from_the_next_rotation(
    client: TestClient, engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_SLIDING, "false")
    sign_in(client, _EMAIL, _PASSWORD)
    earlier = utcnow().replace(microsecond=0) + timedelta(hours=1)
    _set_the_expiry(engine, earlier)

    monkeypatch.setenv(_SLIDING, "true")

    assert _refresh_after_the_grace(client).status_code == 200  # type: ignore[attr-defined]
    assert _row(engine).expires_at > earlier
    assert _exp(_refresh_cookie(client)) == _row(engine).expires_at


# --- 不正な値


@pytest.mark.parametrize("value", [0, -1, "abc", "", 1.5, True, MAX_REFRESH_TOKEN_EXPIRES_SECONDS + 1])
def test_an_unusable_lifetime_is_refused(
    client: TestClient, system_admin_headers: dict[str, str], value: object
) -> None:
    response = client.put("/api/admin/config", headers=system_admin_headers, json={"values": {_PERIOD: value}})
    assert response.status_code == 400
    assert response.json()["detail"] == {"error": "invalid_setting_value", "key": _PERIOD}


@pytest.mark.parametrize("value", ["abc", 1])
def test_an_unusable_switch_is_refused(client: TestClient, system_admin_headers: dict[str, str], value: object) -> None:
    response = client.put("/api/admin/config", headers=system_admin_headers, json={"values": {_SLIDING: value}})
    assert response.status_code == 400
    assert response.json()["detail"] == {"error": "invalid_setting_value", "key": _SLIDING}


def test_usable_values_are_saved_and_can_be_cleared(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    saved = client.put(
        "/api/admin/config", headers=system_admin_headers, json={"values": {_PERIOD: 3600, _SLIDING: False}}
    )
    assert saved.status_code == 200
    assert settings.refresh_token_expires_seconds == 3600
    assert settings.refresh_token_sliding_enabled is False

    cleared = client.put(
        "/api/admin/config", headers=system_admin_headers, json={"values": {_PERIOD: None, _SLIDING: None}}
    )
    assert cleared.status_code == 200
    assert settings.refresh_token_expires_seconds == 14 * 24 * 3600
    assert settings.refresh_token_sliding_enabled is True


@pytest.mark.parametrize("value", ["0", "-5", "abc", str(MAX_REFRESH_TOKEN_EXPIRES_SECONDS + 1)])
def test_an_unusable_value_from_the_environment_falls_back(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(_PERIOD, value)
    assert settings.refresh_token_expires_seconds == 14 * 24 * 3600
    # 500 にならず、普通にログインできる
    sign_in(client, _EMAIL, _PASSWORD)
