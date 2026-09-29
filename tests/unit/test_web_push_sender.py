"""Web Push の送り手（ADR-0047）。通知サービスへは行かず、送ろうとした要求を見る。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription
from bounded_contexts.notification.domain.services.push_sender import PushMessage, PushOutcome
from bounded_contexts.notification.infrastructure.web_push_sender import WebPushSender


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "vapid.pem"
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return path


@pytest.fixture
def subscription() -> PushSubscription:
    """ブラウザが作る購読と同じ形（端末側の鍵を本物で作る）。"""
    device_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = device_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return PushSubscription(
        user_id=1,
        endpoint="https://push.example.test/v1/device-1",
        p256dh=_b64url(p256dh),
        auth=_b64url(b"0123456789abcdef"),
    )


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.reason = "reason"
        self.text = ""
        self.headers: dict[str, str] = {}


class _Requests:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response(self.status_code)


def _install(monkeypatch: pytest.MonkeyPatch, status_code: int) -> _Requests:
    import pywebpush

    fake = _Requests(status_code)
    monkeypatch.setattr(pywebpush, "requests", fake)
    return fake


_MESSAGE = PushMessage(notification_id=7, title="題", body="本文", link_url="/items")


def test_it_is_off_until_both_the_key_and_the_contact_are_set(key_file: Path) -> None:
    assert not WebPushSender("", "mailto:ops@example.test").enabled
    assert not WebPushSender(str(key_file), "").enabled
    assert WebPushSender(str(key_file), "mailto:ops@example.test").enabled


def test_the_public_key_is_the_uncompressed_point(key_file: Path) -> None:
    public_key = WebPushSender(str(key_file), "mailto:ops@example.test").public_key()

    assert public_key is not None
    raw = base64.urlsafe_b64decode(public_key + "=")
    assert len(raw) == 65
    assert raw[0] == 0x04


def test_an_unreadable_key_is_off_not_a_crash(tmp_path: Path, subscription: PushSubscription) -> None:
    sender = WebPushSender(str(tmp_path / "missing.pem"), "mailto:ops@example.test")

    assert sender.public_key() is None
    assert sender.send(subscription, _MESSAGE) is PushOutcome.FAILED


def test_sends_an_encrypted_signed_request(
    key_file: Path, subscription: PushSubscription, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = _install(monkeypatch, 201)
    sender = WebPushSender(str(key_file), "mailto:ops@example.test")

    assert sender.send(subscription, _MESSAGE) is PushOutcome.DELIVERED

    [call] = requests.calls
    assert call["url"] == subscription.endpoint
    headers = call["headers"]
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["ttl"] == str(24 * 60 * 60)
    assert headers["Authorization"].startswith("vapid t=")
    assert f"k={sender.public_key()}" in headers["Authorization"]
    # 本文は暗号化されている（平文の題が見えない）
    assert "題".encode() not in call["data"]
    assert json.dumps("題", ensure_ascii=False).encode() not in call["data"]


@pytest.mark.parametrize(
    ("status_code", "outcome"), [(404, PushOutcome.GONE), (410, PushOutcome.GONE), (500, PushOutcome.FAILED)]
)
def test_maps_the_answer(
    key_file: Path,
    subscription: PushSubscription,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    outcome: PushOutcome,
) -> None:
    _install(monkeypatch, status_code)

    assert WebPushSender(str(key_file), "mailto:ops@example.test").send(subscription, _MESSAGE) is outcome
