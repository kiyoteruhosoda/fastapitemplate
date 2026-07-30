"""パスキーの登録・ログインを本物の署名で通す。

``PyWebAuthnRelyingParty`` を差し替えずに、テスト用のソフトウェア認証器
（``software_authenticator``）で署名したレスポンスを送る。設定値（RP ID・
オリジン）からチャレンジ発行・署名検証・トークン発行までが一続きで動くことを
確認する。
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.integration.api.software_authenticator import SoftwareAuthenticator

# 既定の WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN と揃える
RP_ID = "localhost"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def authenticator() -> SoftwareAuthenticator:
    return SoftwareAuthenticator(rp_id=RP_ID, origin=ORIGIN)


def _register(
    client: TestClient,
    headers: dict[str, str],
    authenticator: SoftwareAuthenticator,
    name: str | None,
) -> httpx.Response:
    challenge = client.post("/api/account/security/passkeys/registration", headers=headers)
    assert challenge.status_code == 200, challenge.text
    body = challenge.json()
    return client.post(
        "/api/account/security/passkeys",
        headers=headers,
        json={
            "challenge_id": body["challenge_id"],
            "credential": authenticator.register(body["public_key"]["challenge"]),
            "name": name,
        },
    )


def test_register_then_sign_in_with_a_real_signature(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    registration = _register(client, admin_headers, authenticator, "Test key")
    assert registration.status_code == 201, registration.text
    assert registration.json()["transports"] == ["internal"]

    client.cookies.clear()
    challenge = client.post("/api/auth/passkey/challenge").json()
    login = client.post(
        "/api/auth/passkey/login",
        json={
            "challenge_id": challenge["challenge_id"],
            "credential": authenticator.authenticate(challenge["public_key"]["challenge"]),
        },
    )
    assert login.status_code == 200, login.text

    # 発行されたトークンがそのまま使えること
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


def test_signing_in_records_the_usage(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    """署名カウンタと最終使用日時が更新される（資格情報の複製検出の土台）。"""
    from bounded_contexts.account_security.infrastructure.account_security_models import (
        PasskeyCredentialRecord,
    )

    assert _register(client, admin_headers, authenticator, None).status_code == 201
    before = client.get("/api/account/security/passkeys", headers=admin_headers).json()
    assert before[0]["last_used_at"] is None

    challenge = client.post("/api/auth/passkey/challenge").json()
    assert (
        client.post(
            "/api/auth/passkey/login",
            json={
                "challenge_id": challenge["challenge_id"],
                "credential": authenticator.authenticate(challenge["public_key"]["challenge"]),
            },
        ).status_code
        == 200
    )

    after = client.get("/api/account/security/passkeys", headers=admin_headers).json()
    assert after[0]["last_used_at"] is not None

    from shared.kernel.database.db import get_session_factory

    with get_session_factory()() as session:
        record = session.get(PasskeyCredentialRecord, after[0]["id"])
        assert record is not None
        assert record.sign_count == authenticator.sign_count


def test_a_signature_for_another_origin_is_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    """フィッシングサイトからの署名は通らない（オリジンが検証される）。"""
    attacker = SoftwareAuthenticator(rp_id=RP_ID, origin="https://phishing.example")
    response = _register(client, admin_headers, attacker, None)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"


def test_a_replayed_challenge_is_rejected(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    """同じチャレンジで 2 度ログインできない。"""
    assert _register(client, admin_headers, authenticator, None).status_code == 201

    client.cookies.clear()
    challenge = client.post("/api/auth/passkey/challenge").json()
    payload = {
        "challenge_id": challenge["challenge_id"],
        "credential": authenticator.authenticate(challenge["public_key"]["challenge"]),
    }
    assert client.post("/api/auth/passkey/login", json=payload).status_code == 200

    replay = client.post("/api/auth/passkey/login", json=payload)
    assert replay.status_code == 400
    assert replay.json()["detail"]["error"] == "challenge_not_found"


def test_a_signature_for_a_different_challenge_is_rejected(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    assert _register(client, admin_headers, authenticator, None).status_code == 201

    client.cookies.clear()
    stale = client.post("/api/auth/passkey/challenge").json()
    fresh = client.post("/api/auth/passkey/challenge").json()

    response = client.post(
        "/api/auth/passkey/login",
        json={
            # 新しいチャレンジ ID に、古いチャレンジで作った署名を添える
            "challenge_id": fresh["challenge_id"],
            "credential": authenticator.authenticate(stale["public_key"]["challenge"]),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"
