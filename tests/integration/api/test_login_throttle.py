"""ログインの失敗を宛名ごとに数えて、しばらく断る（ADR-0058）。

見たいのは、**上限で 429 になること**（正しいパスワードでも）・**時間が過ぎれば
入れること**・**二要素のコードの間違いも数えること**・**未知の宛名も同じに扱うこと**・
**再設定の要求も数えること**・**断り始めたことが監査に残ること**。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from shared.domain.auth import master_data
from shared.kernel.timestamps import utcnow

LOGIN = "/api/auth/login"
ADMIN = master_data.DEFAULT_ADMIN_EMAIL
PASSWORD = master_data.DEFAULT_ADMIN_PASSWORD
RIGHT = {"email": ADMIN, "password": PASSWORD}


@pytest.fixture(autouse=True)
def _small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """3 回で断る（既定の 5 回だと試行が長い）。"""
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")


def _fail(client: TestClient, email: str, times: int) -> None:
    for _ in range(times):
        assert client.post(LOGIN, json={"email": email, "password": "wrong-password"}).status_code == 401


def test_the_limit_refuses_even_the_right_password(client: TestClient) -> None:
    _fail(client, ADMIN, 3)

    refused = client.post(LOGIN, json=RIGHT)

    assert refused.status_code == 429
    assert refused.json()["detail"]["error"] == "too_many_attempts"
    # いつ再開できるかを本文とヘッダーの両方で
    assert refused.json()["detail"]["retry_after_seconds"] > 0
    assert refused.headers["Retry-After"] == str(refused.json()["detail"]["retry_after_seconds"])


def test_the_lock_lifts_when_the_time_has_passed(client: TestClient) -> None:
    _fail(client, ADMIN, 3)
    assert client.post(LOGIN, json=RIGHT).status_code == 429

    later = utcnow() + timedelta(seconds=901)
    with patch("presentation.fastapi.services.login_service.utcnow", return_value=later):
        assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_wrong_second_factor_codes_are_counted(client: TestClient, admin_headers: dict[str, str]) -> None:
    """パスワードが分かった相手に、6 桁のコードを総当たりさせない。"""
    enrollment = client.post("/api/account/security/two-factor/enrollment", headers=admin_headers)
    assert enrollment.status_code == 200, enrollment.text
    secret = str(enrollment.json()["secret"])
    confirmed = client.post(
        "/api/account/security/two-factor/confirmation",
        headers=admin_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmed.status_code == 200, confirmed.text

    wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
    for _ in range(3):
        assert client.post(LOGIN, json={**RIGHT, "totp_code": wrong}).status_code == 401

    refused = client.post(LOGIN, json={**RIGHT, "totp_code": pyotp.TOTP(secret).now()})
    assert refused.status_code == 429


def test_an_unknown_address_is_refused_the_same_way(client: TestClient) -> None:
    # 実在するものだけが 429 になるなら、それで存在が分かってしまう
    _fail(client, "nobody@example.com", 3)

    refused = client.post(LOGIN, json={"email": "nobody@example.com", "password": "anything"})
    assert refused.status_code == 429


def test_one_address_does_not_lock_another(client: TestClient) -> None:
    _fail(client, "nobody@example.com", 3)
    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_a_successful_login_forgets_the_failures(client: TestClient) -> None:
    _fail(client, ADMIN, 2)
    assert client.post(LOGIN, json=RIGHT).status_code == 200

    # 忘れているので、また 2 回までは 401 のまま
    _fail(client, ADMIN, 2)
    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_locking_is_recorded_in_the_audit_log(client: TestClient, admin_headers: dict[str, str]) -> None:
    _fail(client, "nobody@example.com", 3)
    # 断っているあいだの試行も残る（当たられていることが見える）
    assert client.post(LOGIN, json={"email": "nobody@example.com", "password": "x"}).status_code == 429

    locked = client.get("/api/admin/audit-logs", headers=admin_headers, params={"event_type": "login.locked"}).json()
    assert [entry["reason"] for entry in locked["entries"]] == ["unknown_email"]
    failed = client.get("/api/admin/audit-logs", headers=admin_headers, params={"event_type": "login.failed"}).json()
    assert [entry["reason"] for entry in failed["entries"]].count("locked") == 1


def test_a_disabled_policy_never_refuses(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "0")
    _fail(client, ADMIN, 6)
    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_password_reset_requests_are_counted_even_when_they_succeed(client: TestClient) -> None:
    for _ in range(3):
        assert client.post("/api/auth/forgot-password", json={"email": ADMIN}).status_code == 200

    refused = client.post("/api/auth/forgot-password", json={"email": ADMIN})
    assert refused.status_code == 429
    # ログインの籠とは別。再設定を叩かれてもログインは断られない
    assert client.post(LOGIN, json=RIGHT).status_code == 200
