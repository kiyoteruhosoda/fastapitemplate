"""ログインの控えとリフレッシュトークンの振り替え（ADR-0091）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
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
from shared.kernel.timestamps import utcnow
from tests.conftest import sign_in

_EMAIL = master_data.DEFAULT_ADMIN_EMAIL
_PASSWORD = master_data.DEFAULT_ADMIN_PASSWORD
_REFRESH = "/api/auth/refresh"


def _headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def _refresh_cookie(client: TestClient) -> str:
    return client.cookies.get(REFRESH_TOKEN_COOKIE, path=REFRESH_COOKIE_PATH) or ""


def _present(client: TestClient, token: str) -> int:
    """手元に控えたトークンを更新の口へ出す。"""
    client.cookies.delete(REFRESH_TOKEN_COOKIE)
    client.cookies.set(REFRESH_TOKEN_COOKIE, token, path=REFRESH_COOKIE_PATH)
    return client.post(_REFRESH, headers=_headers(client)).status_code


def _after_the_grace() -> datetime:
    return utcnow() + timedelta(seconds=REUSE_GRACE_SECONDS + 1)


def test_logging_out_ends_the_refresh_token_taken_before(client: TestClient) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    taken = _refresh_cookie(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert _present(client, taken) == 401


def test_logging_out_clears_the_cookies(client: TestClient) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    client.post("/api/auth/logout")
    assert not client.cookies.get(LOGOUT_TOKEN_COOKIE, path=LOGOUT_COOKIE_PATH)
    assert not _refresh_cookie(client)


def test_logging_out_leaves_other_devices_signed_in(client: TestClient, other_client: TestClient) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    sign_in(other_client, _EMAIL, _PASSWORD)
    client.post("/api/auth/logout")
    assert other_client.post(_REFRESH, headers=_headers(other_client)).status_code == 200


def test_logging_out_without_a_session_is_fine(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/api/auth/logout").status_code == 200


def test_a_used_token_is_refused_and_ends_only_that_sign_in(
    client: TestClient, other_client: TestClient, engine: sa.Engine
) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    sign_in(other_client, _EMAIL, _PASSWORD)
    used = _refresh_cookie(client)
    assert client.post(_REFRESH, headers=_headers(client)).status_code == 200
    latest = _refresh_cookie(client)

    with patch("presentation.fastapi.services.refresh_sessions.utcnow", return_value=_after_the_grace()):
        assert _present(client, used) == 401
    # 盗まれた 1 本で、今の 1 本も止まる（どちらが本人か分からない）
    assert _present(client, latest) == 401
    assert other_client.post(_REFRESH, headers=_headers(other_client)).status_code == 200

    with Session(engine) as session:
        recorded = session.scalars(
            sa.select(AuditLogModel.event_type).where(
                AuditLogModel.event_type == AuditEventType.REFRESH_TOKEN_REUSED.value
            )
        ).all()
    assert len(recorded) == 1


def test_a_refresh_racing_from_another_tab_does_not_sign_out(client: TestClient) -> None:
    """負けた側はアクセストークンだけを受け取り、Cookie は勝った側のものが残る。"""
    sign_in(client, _EMAIL, _PASSWORD)
    first = _refresh_cookie(client)
    assert client.post(_REFRESH, headers=_headers(client)).status_code == 200
    winner = _refresh_cookie(client)
    assert winner != first

    client.cookies.delete(REFRESH_TOKEN_COOKIE)
    client.cookies.set(REFRESH_TOKEN_COOKIE, first, path=REFRESH_COOKIE_PATH)
    raced = client.post(_REFRESH, headers=_headers(client))
    assert raced.status_code == 200
    issued = raced.headers.get_list("set-cookie")
    assert not any(cookie.startswith(f"{REFRESH_TOKEN_COOKIE}=") for cookie in issued)
    assert client.get("/api/auth/me").status_code == 200

    assert _present(client, winner) == 200


def test_the_row_follows_the_rotation(client: TestClient, engine: sa.Engine) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    client.post(_REFRESH, headers=_headers(client))
    with Session(engine) as session:
        rows = session.scalars(sa.select(RefreshSession)).all()
    assert len(rows) == 1
    assert rows[0].previous_jti is not None
    assert rows[0].current_jti != rows[0].previous_jti


def test_switching_roles_keeps_the_same_sign_in(client: TestClient, engine: sa.Engine) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    assert client.post("/api/auth/switch-role", json={"role": None}, headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(RefreshSession)) == 1
    assert client.post(_REFRESH, headers=_headers(client)).status_code == 200


def test_a_signed_out_session_cannot_reissue_with_the_access_token_it_kept(client: TestClient) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    kept = client.cookies["access_token"]
    client.post("/api/auth/logout")
    client.cookies.set("access_token", kept)
    assert client.post("/api/auth/switch-role", json={"role": None}, headers=headers).status_code == 401


def test_a_token_without_a_session_is_refused(client: TestClient) -> None:
    """控えの仕組みより前に出したトークン。使い回しを見分けられないので通さない。"""
    sign_in(client, _EMAIL, _PASSWORD)
    now = datetime.now(UTC)
    old = jwt.encode(
        {
            "sub": "1",
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "iat": now,
            "exp": now + timedelta(days=1),
            "type": "refresh",
            "tenant": None,
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    assert _present(client, old) == 401


def test_a_logout_token_cannot_refresh(client: TestClient) -> None:
    sign_in(client, _EMAIL, _PASSWORD)
    logout_token = client.cookies.get(LOGOUT_TOKEN_COOKIE, path=LOGOUT_COOKIE_PATH) or ""
    assert logout_token
    assert _present(client, logout_token) == 401
