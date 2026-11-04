"""DPoP の証明の確かめ（ADR-0103）。assay（idp の ADR-0075）と同じ幅・同じ断り方。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bounded_contexts.identity_federation.domain.exceptions import DpopProofRejectedError
from bounded_contexts.identity_federation.domain.value_objects.dpop_proof import (
    MAX_CLOCK_AHEAD,
    MAX_PROOF_AGE,
    DpopProofRequirements,
)
from bounded_contexts.identity_federation.infrastructure.pyjwt_dpop_proof_verifier import (
    PyJwtDpopProofVerifier,
    jwk_thumbprint,
)
from tests.dpop_device_key import DeviceKey

_URI = "https://app.example.test/api/app/me"
_TOKEN = "access-token"
_NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _requirements(**overrides: object) -> DpopProofRequirements:
    values: dict[str, object] = {"method": "GET", "uri": _URI, "access_token": _TOKEN, "now": _NOW}
    values.update(overrides)
    return DpopProofRequirements(**values)  # type: ignore[arg-type]


def _at(delta: timedelta) -> int:
    return int((_NOW + delta).timestamp())


def test_a_fresh_proof_yields_the_key_thumbprint() -> None:
    device = DeviceKey()
    proof = device.proof("GET", _URI, _TOKEN, iat=_at(timedelta()), jti="j1")

    verified = PyJwtDpopProofVerifier().verify(proof, _requirements())

    assert verified.jkt == device.thumbprint
    assert verified.jti == "j1"
    assert verified.retain_until == _NOW + MAX_PROOF_AGE


def test_the_thumbprint_follows_rfc_7638() -> None:
    # RFC 7638 §3.1 の例と同じ手順（EC の必須欄を辞書順に並べる）。値は assay の試験と同じ。
    x = "f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU"
    y = "x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0"
    assert len(jwk_thumbprint(x, y)) == 43
    assert jwk_thumbprint(x, y) != jwk_thumbprint(y, x)


def test_the_query_of_htu_is_ignored() -> None:
    device = DeviceKey()
    proof = device.proof("GET", "https://APP.example.test/api/app/me?x=1#y", _TOKEN, iat=_at(timedelta()))
    assert PyJwtDpopProofVerifier().verify(proof, _requirements()).jkt == device.thumbprint


@pytest.mark.parametrize(
    ("method", "uri", "token"),
    [
        ("POST", _URI, _TOKEN),
        ("GET", "https://app.example.test/api/app/other", _TOKEN),
        ("GET", "https://evil.example.test/api/app/me", _TOKEN),
        ("GET", _URI, "another-token"),
        ("GET", _URI, None),
    ],
)
def test_a_proof_for_another_request_is_rejected(method: str, uri: str, token: str | None) -> None:
    proof = DeviceKey().proof(method, uri, token, iat=_at(timedelta()))
    with pytest.raises(DpopProofRejectedError):
        PyJwtDpopProofVerifier().verify(proof, _requirements())


@pytest.mark.parametrize(
    ("delta", "accepted"),
    [
        (-MAX_PROOF_AGE, True),
        (-MAX_PROOF_AGE - timedelta(seconds=1), False),
        (MAX_CLOCK_AHEAD, True),
        (MAX_CLOCK_AHEAD + timedelta(seconds=1), False),
    ],
)
def test_iat_must_be_inside_the_window(delta: timedelta, accepted: bool) -> None:
    proof = DeviceKey().proof("GET", _URI, _TOKEN, iat=_at(delta))
    if accepted:
        PyJwtDpopProofVerifier().verify(proof, _requirements())
    else:
        with pytest.raises(DpopProofRejectedError):
            PyJwtDpopProofVerifier().verify(proof, _requirements())


def test_a_proof_signed_by_another_key_is_rejected() -> None:
    owner, thief = DeviceKey(), DeviceKey()
    # ヘッダーには持ち主の公開鍵を書き、盗んだ側の鍵で署名する
    forged = thief.proof("GET", _URI, _TOKEN, iat=_at(timedelta()), header={"typ": "dpop+jwt", "jwk": owner.jwk})
    with pytest.raises(DpopProofRejectedError):
        PyJwtDpopProofVerifier().verify(forged, _requirements())


@pytest.mark.parametrize(
    "header",
    [
        {"typ": "JWT"},
        {"typ": "dpop+jwt"},
        {"typ": "dpop+jwt", "jwk": {"kty": "RSA", "n": "AQAB", "e": "AQAB"}},
    ],
)
def test_the_header_must_carry_a_public_p256_key(header: dict[str, object]) -> None:
    device = DeviceKey()
    if header.get("typ") == "JWT":
        header = {**header, "jwk": device.jwk}
    proof = device.proof("GET", _URI, _TOKEN, iat=_at(timedelta()), header=header)
    with pytest.raises(DpopProofRejectedError):
        PyJwtDpopProofVerifier().verify(proof, _requirements())


def test_a_private_key_in_the_header_is_rejected() -> None:
    device = DeviceKey()
    proof = device.proof(
        "GET", _URI, _TOKEN, iat=_at(timedelta()), header={"typ": "dpop+jwt", "jwk": {**device.jwk, "d": "AAAA"}}
    )
    with pytest.raises(DpopProofRejectedError):
        PyJwtDpopProofVerifier().verify(proof, _requirements())


def test_garbage_is_rejected() -> None:
    with pytest.raises(DpopProofRejectedError):
        PyJwtDpopProofVerifier().verify("not-a-jwt", _requirements())
