"""入り口を作り替える操作は、入り直したばかりのときだけ（ADR-0076 §10）。

盗まれたセッションでパスキーを足す・メールを替えると、そのあとはパスワードも二要素も
無しに入り続けられる。最後に**実際に**サインインしてから ``RECENT_SIGN_IN_SECONDS``
（既定 600 秒）を過ぎていたら 403 ``reauthentication_required`` で断る。

「古いセッション」は、11 分前にサインインし、そのあと更新だけしたものとして作る
（更新は入り直しではないので、サインインした時刻は古いまま引き継がれる）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from presentation.fastapi.services.token_service import SIGNED_IN_LONG_AGO, _authenticated_at_of
from shared.domain.auth import master_data
from tests.conftest import sign_in

_EMAIL = master_data.DEFAULT_ADMIN_EMAIL
_PASSWORD = master_data.DEFAULT_ADMIN_PASSWORD
_REGISTRATION = "/api/account/security/passkeys/registration"


@contextmanager
def _clock_set_back(minutes: int) -> Iterator[None]:
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = datetime.now(UTC) - timedelta(minutes=minutes)
    with patch("presentation.fastapi.services.token_service.datetime", clock):
        yield


def _headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def _stale_session(client: TestClient) -> dict[str, str]:
    """11 分前にサインインし、いま更新だけしたセッション。"""
    with _clock_set_back(11):
        sign_in(client, _EMAIL, _PASSWORD)
    refreshed = client.post("/api/auth/refresh", headers=_headers(client))
    assert refreshed.status_code == 200, refreshed.text
    return _headers(client)


def _refused(response_status: int, body: dict[str, object]) -> bool:
    detail = body.get("detail")
    return response_status == 403 and isinstance(detail, dict) and detail.get("error") == "reauthentication_required"


def test_a_fresh_sign_in_may_add_a_passkey(client: TestClient) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    assert client.post(_REGISTRATION, headers=headers).status_code == 200


def test_a_stale_session_may_not_add_or_remove_passkeys(client: TestClient) -> None:
    headers = _stale_session(client)

    started = client.post(_REGISTRATION, headers=headers)
    assert _refused(started.status_code, started.json())
    completed = client.post(
        "/api/account/security/passkeys", headers=headers, json={"challenge_id": "x", "credential": {}, "name": "x"}
    )
    assert _refused(completed.status_code, completed.json())
    removed = client.delete("/api/account/security/passkeys/1", headers=headers)
    assert _refused(removed.status_code, removed.json())


def test_switching_roles_does_not_freshen_the_sign_in(client: TestClient) -> None:
    _stale_session(client)
    switched = client.post("/api/auth/switch-role", headers=_headers(client), json={"role": None})
    assert switched.status_code == 200, switched.text

    started = client.post(_REGISTRATION, headers=_headers(client))
    assert _refused(started.status_code, started.json())


def test_signing_in_again_lifts_the_refusal(client: TestClient) -> None:
    _stale_session(client)
    headers = sign_in(client, _EMAIL, _PASSWORD)
    assert client.post(_REGISTRATION, headers=headers).status_code == 200


def test_a_stale_session_may_not_change_the_email(client: TestClient) -> None:
    headers = _stale_session(client)
    changed = client.put("/api/auth/me", headers=headers, json={"email": "taken@example.com", "username": "admin"})
    assert _refused(changed.status_code, changed.json())


def test_a_stale_session_may_still_change_the_display_name(client: TestClient) -> None:
    """表示名は入り口ではないので、入り直しは求めない。"""
    headers = _stale_session(client)
    changed = client.put("/api/auth/me", headers=headers, json={"email": _EMAIL, "username": "renamed"})
    assert changed.status_code == 200, changed.text


def test_a_fresh_sign_in_may_change_the_email(client: TestClient) -> None:
    headers = sign_in(client, _EMAIL, _PASSWORD)
    changed = client.put("/api/auth/me", headers=headers, json={"email": "fresh@example.com", "username": "admin"})
    assert changed.status_code == 200, changed.text


def test_a_token_without_the_sign_in_time_counts_as_long_ago() -> None:
    """この仕組みより前のトークンが、更新 1 回で「入り直したばかり」に化けない。"""
    assert _authenticated_at_of({}) == SIGNED_IN_LONG_AGO
    assert _authenticated_at_of({"auth_time": "not-a-number"}) == SIGNED_IN_LONG_AGO
