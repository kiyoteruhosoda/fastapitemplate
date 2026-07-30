"""テスト用のソフトウェア認証器（WebAuthn）。

実物の認証器が使えないため、ブラウザ＋認証器が返すものと同じ形の
レスポンスを組み立てて署名する。これで登録・認証の検証パス
（``PyWebAuthnRelyingParty``）を本物の署名で確認できる。

出力は WebAuthn の仕様どおりの形（base64url 文字列の JSON）で、
``frontend/src/services/webauthn.ts`` がブラウザから作るものと同じ。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# authenticatorData のフラグ（WebAuthn 仕様）
_FLAG_USER_PRESENT = 0x01
_FLAG_USER_VERIFIED = 0x04
_FLAG_ATTESTED_CREDENTIAL_DATA = 0x40

_COSE_ES256 = -7


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _client_data(*, ceremony: str, challenge: str, origin: str) -> bytes:
    return json.dumps(
        {
            "type": ceremony,
            "challenge": challenge,
            "origin": origin,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _cose_public_key(public_key: ec.EllipticCurvePublicKey) -> bytes:
    numbers = public_key.public_numbers()
    return cbor2.dumps(
        {
            1: 2,  # kty: EC2
            3: _COSE_ES256,  # alg: ES256
            -1: 1,  # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }
    )


def _authenticator_data(*, rp_id: str, flags: int, sign_count: int, attested: bytes = b"") -> bytes:
    return hashlib.sha256(rp_id.encode("utf-8")).digest() + bytes([flags]) + struct.pack(">I", sign_count) + attested


@dataclass
class SoftwareAuthenticator:
    """1 つのパスキーを持つ認証器。"""

    rp_id: str = "localhost"
    origin: str = "http://localhost:5173"
    aaguid: bytes = b"\x00" * 16
    sign_count: int = 0
    credential_id: bytes = field(default_factory=lambda: os.urandom(32))
    _private_key: ec.EllipticCurvePrivateKey = field(default_factory=lambda: ec.generate_private_key(ec.SECP256R1()))

    def register(self, challenge: str) -> dict[str, Any]:
        """``navigator.credentials.create`` が返すものと同じ形を組み立てる。"""
        client_data = _client_data(ceremony="webauthn.create", challenge=challenge, origin=self.origin)
        attested = (
            self.aaguid
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + _cose_public_key(self._private_key.public_key())
        )
        auth_data = _authenticator_data(
            rp_id=self.rp_id,
            flags=_FLAG_USER_PRESENT | _FLAG_USER_VERIFIED | _FLAG_ATTESTED_CREDENTIAL_DATA,
            sign_count=self.sign_count,
            attested=attested,
        )
        # fmt="none": 認証器の出自を証明しない（本テンプレートの登録方針と同じ）
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": base64url(self.credential_id),
            "rawId": base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": base64url(client_data),
                "attestationObject": base64url(attestation_object),
                "transports": ["internal"],
            },
        }

    def authenticate(self, challenge: str) -> dict[str, Any]:
        """``navigator.credentials.get`` が返すものと同じ形を組み立てる。"""
        self.sign_count += 1
        client_data = _client_data(ceremony="webauthn.get", challenge=challenge, origin=self.origin)
        auth_data = _authenticator_data(
            rp_id=self.rp_id,
            flags=_FLAG_USER_PRESENT | _FLAG_USER_VERIFIED,
            sign_count=self.sign_count,
        )
        signature = self._private_key.sign(
            auth_data + hashlib.sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": base64url(self.credential_id),
            "rawId": base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": base64url(client_data),
                "authenticatorData": base64url(auth_data),
                "signature": base64url(signature),
                "userHandle": None,
            },
        }


__all__ = ["SoftwareAuthenticator", "base64url"]
