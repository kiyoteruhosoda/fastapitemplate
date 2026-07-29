"""パスキー（WebAuthn）の登録・一覧・削除・ログイン。

実際の認証器は使えないため、``WebAuthnRelyingParty`` を偽の実装へ差し替えて
アプリケーション側の流れ（チャレンジの発行・消費、資格情報の保存、トークン
発行）を検証する。署名検証そのものはライブラリの責務。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from bounded_contexts.account_security.domain.exceptions import (
    PasskeyVerificationError,
)
from bounded_contexts.account_security.domain.services.webauthn_relying_party import (
    PublicKeyOptions,
    VerifiedAssertion,
    VerifiedRegistration,
)
from bounded_contexts.account_security.presentation.dependencies import (
    build_relying_party,
)


@dataclass
class FakeRelyingParty:
    """チャレンジを固定し、``credential`` の中身をそのまま信じる偽 RP。"""

    challenge: str = "Y2hhbGxlbmdl"
    accepted_challenges: list[str] = field(default_factory=list)

    def create_registration_options(
        self, *, user_id: int, user_name: str, display_name: str,
        exclude_credential_ids: Sequence[str] = (),
    ) -> PublicKeyOptions:
        return PublicKeyOptions(
            public_key={
                "challenge": self.challenge,
                "user": {"name": user_name, "displayName": display_name},
                "excludeCredentials": list(exclude_credential_ids),
            },
            challenge=self.challenge,
        )

    def verify_registration(
        self, *, credential: Mapping[str, Any], expected_challenge: str
    ) -> VerifiedRegistration:
        self.accepted_challenges.append(expected_challenge)
        if credential.get("id") == "reject":
            raise PasskeyVerificationError
        return VerifiedRegistration(
            credential_id=str(credential["id"]),
            public_key="cHVibGljLWtleQ",
            sign_count=1,
            attestation_format="none",
            aaguid="00000000-0000-0000-0000-000000000000",
            backup_eligible=True,
            backup_state=False,
        )

    def create_authentication_options(
        self, *, allow_credential_ids: Sequence[str] = ()
    ) -> PublicKeyOptions:
        return PublicKeyOptions(
            public_key={"challenge": self.challenge}, challenge=self.challenge
        )

    def verify_authentication(
        self, *, credential: Mapping[str, Any], expected_challenge: str,
        stored_public_key: str, stored_sign_count: int,
    ) -> VerifiedAssertion:
        if credential.get("id") == "reject":
            raise PasskeyVerificationError
        return VerifiedAssertion(
            credential_id=str(credential["id"]), sign_count=stored_sign_count + 1
        )

    def extract_credential_id(self, credential: Mapping[str, Any]) -> str | None:
        value = credential.get("id")
        return value if isinstance(value, str) else None


@pytest.fixture
def relying_party(app) -> FakeRelyingParty:
    fake = FakeRelyingParty()
    app.dependency_overrides[build_relying_party] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def _register(client, headers, credential_id: str = "credential-1", **extra):
    challenge = client.post(
        "/api/account/security/passkeys/registration", headers=headers
    )
    assert challenge.status_code == 200, challenge.text
    return client.post(
        "/api/account/security/passkeys",
        headers=headers,
        json={
            "challenge_id": challenge.json()["challenge_id"],
            "credential": {"id": credential_id, "response": {"transports": ["usb"]}},
            **extra,
        },
    )


def test_passkey_list_requires_authentication(client, relying_party) -> None:
    client.cookies.clear()
    assert client.get("/api/account/security/passkeys").status_code == 401


def test_real_relying_party_produces_browser_ready_options(client, admin_headers) -> None:
    """偽物を挟まず、設定値から実際の WebAuthn オプションが組み立てられること。"""
    response = client.post(
        "/api/account/security/passkeys/registration", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    public_key = response.json()["public_key"]
    assert public_key["rp"]["id"] == "localhost"
    assert public_key["user"]["name"] == "admin@example.com"
    assert public_key["challenge"]
    assert public_key["pubKeyCredParams"]

    login_options = client.post("/api/auth/passkey/challenge").json()["public_key"]
    # ログインは資格情報を指定しない（メールアドレスの入力が不要になる）
    assert login_options["allowCredentials"] == []


def test_registration_stores_the_credential(client, admin_headers, relying_party) -> None:
    response = _register(client, admin_headers, name="Yubikey")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Yubikey"
    assert body["transports"] == ["usb"]

    listed = client.get("/api/account/security/passkeys", headers=admin_headers).json()
    assert [item["name"] for item in listed] == ["Yubikey"]


def test_registration_challenge_is_single_use(client, admin_headers, relying_party) -> None:
    challenge = client.post(
        "/api/account/security/passkeys/registration", headers=admin_headers
    ).json()
    payload = {
        "challenge_id": challenge["challenge_id"],
        "credential": {"id": "credential-1", "response": {}},
    }
    assert client.post(
        "/api/account/security/passkeys", headers=admin_headers, json=payload
    ).status_code == 201

    replay = client.post(
        "/api/account/security/passkeys", headers=admin_headers, json=payload
    )
    assert replay.status_code == 400
    assert replay.json()["detail"]["error"] == "challenge_not_found"


def test_registration_excludes_already_registered_credentials(
    client, admin_headers, relying_party
) -> None:
    _register(client, admin_headers, "credential-1")
    challenge = client.post(
        "/api/account/security/passkeys/registration", headers=admin_headers
    ).json()
    assert challenge["public_key"]["excludeCredentials"] == ["credential-1"]


def test_unnamed_passkey_gets_a_fallback_name(
    client, admin_headers, relying_party
) -> None:
    response = _register(client, admin_headers, "abcdefghij")
    assert response.json()["name"] == "passkey-abcdefgh"


def test_delete_removes_the_passkey(client, admin_headers, relying_party) -> None:
    passkey_id = _register(client, admin_headers).json()["id"]
    assert client.delete(
        f"/api/account/security/passkeys/{passkey_id}", headers=admin_headers
    ).status_code == 204
    assert client.get("/api/account/security/passkeys", headers=admin_headers).json() == []


def test_delete_unknown_passkey_returns_not_found(
    client, admin_headers, relying_party
) -> None:
    response = client.delete(
        "/api/account/security/passkeys/9999", headers=admin_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "passkey_not_found"


def test_login_with_a_registered_passkey(client, admin_headers, relying_party) -> None:
    _register(client, admin_headers)
    client.cookies.clear()

    challenge = client.post("/api/auth/passkey/challenge")
    assert challenge.status_code == 200
    response = client.post(
        "/api/auth/passkey/login",
        json={
            "challenge_id": challenge.json()["challenge_id"],
            "credential": {"id": "credential-1", "response": {}},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_login_with_an_unknown_credential_is_rejected(client, relying_party) -> None:
    challenge = client.post("/api/auth/passkey/challenge").json()
    response = client.post(
        "/api/auth/passkey/login",
        json={
            "challenge_id": challenge["challenge_id"],
            "credential": {"id": "never-registered", "response": {}},
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"


def test_failed_verification_is_reported_as_unauthorized(
    client, admin_headers, relying_party
) -> None:
    response = _register(client, admin_headers, "reject")
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"
    # 検証に失敗した資格情報は保存されない
    assert client.get("/api/account/security/passkeys", headers=admin_headers).json() == []
