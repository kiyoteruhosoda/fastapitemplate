"""Passkey registration and sign-in with real signatures.

Without replacing ``PyWebAuthnRelyingParty``, responses signed by a software authenticator for
tests (``software_authenticator``) are sent. Confirms that everything from the settings (RP ID,
origin) through challenge issuance, signature verification and token issuance works end to end.
"""

from __future__ import annotations

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.integration.api.software_authenticator import SoftwareAuthenticator

# Matches the default WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN
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
) -> httpx2.Response:
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

    # The cookie that was set can be used as is (ADR-0076 §4)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


def test_signing_in_records_the_usage(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    """The signature counter and last-used time are updated (the basis for detecting cloned credentials)."""
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
    """Signatures from a phishing site do not pass (the origin is verified)."""
    attacker = SoftwareAuthenticator(rp_id=RP_ID, origin="https://phishing.example")
    response = _register(client, admin_headers, attacker, None)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"


def test_a_replayed_challenge_is_rejected(
    client: TestClient, admin_headers: dict[str, str], authenticator: SoftwareAuthenticator
) -> None:
    """You cannot sign in twice with the same challenge."""
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
            # Attach a signature made with the old challenge to a new challenge ID
            "challenge_id": fresh["challenge_id"],
            "credential": authenticator.authenticate(stale["public_key"]["challenge"]),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "passkey_verification_failed"
