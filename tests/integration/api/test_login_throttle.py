"""Counting sign-in failures per target and refusing for a while (ADR-0076 §9).

Checked: **429 at the limit** (even with the correct password), **getting in again once time
passes**, **wrong two-factor codes count too**, **unknown targets are treated the same**,
**reset requests count too**, and **the start of refusals is audited**.
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
    """Refuse after 3 (the default of 5 makes the test long)."""
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")


def _fail(client: TestClient, email: str, times: int) -> None:
    for _ in range(times):
        assert client.post(LOGIN, json={"email": email, "password": "wrong-password"}).status_code == 401


def test_the_limit_refuses_even_the_right_password(client: TestClient) -> None:
    _fail(client, ADMIN, 3)

    refused = client.post(LOGIN, json=RIGHT)

    assert refused.status_code == 429
    assert refused.json()["detail"]["error"] == "too_many_attempts"
    # When it can resume, in both the body and the header
    assert refused.json()["detail"]["retry_after_seconds"] > 0
    assert refused.headers["Retry-After"] == str(refused.json()["detail"]["retry_after_seconds"])


def test_the_lock_lifts_when_the_time_has_passed(client: TestClient) -> None:
    _fail(client, ADMIN, 3)
    assert client.post(LOGIN, json=RIGHT).status_code == 429

    later = utcnow() + timedelta(seconds=901)
    with patch("presentation.fastapi.services.login_service.utcnow", return_value=later):
        assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_wrong_second_factor_codes_are_counted(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Someone who knows the password cannot brute-force the 6-digit code."""
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
    # If only existing targets got 429, that would reveal their existence
    _fail(client, "nobody@example.com", 3)

    refused = client.post(LOGIN, json={"email": "nobody@example.com", "password": "anything"})
    assert refused.status_code == 429


def test_one_address_does_not_lock_another(client: TestClient) -> None:
    _fail(client, "nobody@example.com", 3)
    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_a_successful_login_forgets_the_failures(client: TestClient) -> None:
    _fail(client, ADMIN, 2)
    assert client.post(LOGIN, json=RIGHT).status_code == 200

    # Forgotten, so again up to 2 attempts stay 401
    _fail(client, ADMIN, 2)
    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_locking_is_recorded_in_the_audit_log(
    client: TestClient, other_client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    _fail(other_client, "nobody@example.com", 3)
    # Attempts during the refusal are recorded too (so being targeted is visible)
    assert other_client.post(LOGIN, json={"email": "nobody@example.com", "password": "x"}).status_code == 429

    # Failures with an unknown target are system-wide records (ADR-0079 §2). Read by the system administrator
    headers = system_admin_headers
    locked = client.get("/api/admin/audit-logs", headers=headers, params={"event_type": "login.locked"}).json()
    assert [entry["reason"] for entry in locked["entries"]] == ["unknown_email"]
    failed = client.get("/api/admin/audit-logs", headers=headers, params={"event_type": "login.failed"}).json()
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
    # Separate from the sign-in bucket. Hammering reset does not get sign-in refused
    assert client.post(LOGIN, json=RIGHT).status_code == 200
