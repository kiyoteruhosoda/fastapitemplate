"""FCM（HTTP v1）の送り手（ADR-0049）。Google へは行かず、送ろうとした要求を見る。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from bounded_contexts.notification.domain.entities.device_token import DeviceToken
from bounded_contexts.notification.domain.services.push_sender import PushMessage, PushOutcome
from bounded_contexts.notification.infrastructure import fcm_sender
from bounded_contexts.notification.infrastructure.fcm_sender import FcmSender

_TOKEN_URI = "https://oauth2.example.test/token"
_MESSAGE = PushMessage(notification_id=7, title="題", body="本文", link_url="/items")
_DEVICE = DeviceToken(user_id=1, token="device-token")


@pytest.fixture(autouse=True)
def _fresh_token_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fcm_sender, "_token_cache", fcm_sender._AccessTokenCache())


@pytest.fixture
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def account_file(tmp_path: Path, key: rsa.RSAPrivateKey) -> Path:
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    path = tmp_path / "service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "example-project",
                "client_email": "fcm@example-project.iam.gserviceaccount.com",
                "private_key": pem,
                "token_uri": _TOKEN_URI,
            }
        ),
        encoding="utf-8",
    )
    return path


class _Google:
    """OAuth と FCM の代わり。受けた要求を覚え、決めた答えを返す。"""

    def __init__(self, send_status: int = 200, send_body: object | None = None) -> None:
        self.send_status = send_status
        self.send_body = send_body or {"name": "projects/example-project/messages/1"}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == _TOKEN_URI:
            return httpx.Response(200, json={"access_token": "google-access-token", "expires_in": 3599})
        return httpx.Response(self.send_status, json=self.send_body)


def _sender(account_file: Path, google: _Google) -> FcmSender:
    return FcmSender(str(account_file), client=httpx.Client(transport=httpx.MockTransport(google)))


def test_it_is_off_without_a_key_file() -> None:
    assert not FcmSender("").enabled


def test_sends_a_signed_message(account_file: Path, key: rsa.RSAPrivateKey) -> None:
    google = _Google()

    assert _sender(account_file, google).send(_DEVICE, _MESSAGE) is PushOutcome.DELIVERED

    exchange, send = google.requests
    form = dict(pair.split("=", 1) for pair in exchange.content.decode().split("&"))
    assert form["grant_type"] == "urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
    claims = jwt.decode(form["assertion"], key.public_key(), algorithms=["RS256"], audience=_TOKEN_URI)
    assert claims["iss"] == "fcm@example-project.iam.gserviceaccount.com"
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"

    assert str(send.url) == "https://fcm.googleapis.com/v1/projects/example-project/messages:send"
    assert send.headers["Authorization"] == "Bearer google-access-token"
    message = json.loads(send.content)["message"]
    assert message["token"] == "device-token"
    assert message["notification"] == {"title": "題", "body": "本文"}
    assert message["data"] == {"notification_id": "7", "url": "/items"}


def test_the_access_token_is_reused(account_file: Path) -> None:
    google = _Google()
    sender = _sender(account_file, google)

    sender.send(_DEVICE, _MESSAGE)
    sender.send(_DEVICE, _MESSAGE)

    assert [str(r.url) for r in google.requests].count(_TOKEN_URI) == 1


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (404, {"error": {"status": "NOT_FOUND"}}, PushOutcome.GONE),
        (
            400,
            {
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "details": [
                        {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}
                    ],
                }
            },
            PushOutcome.GONE,
        ),
        (400, {"error": {"status": "INVALID_ARGUMENT"}}, PushOutcome.FAILED),
        (503, {"error": {"status": "UNAVAILABLE"}}, PushOutcome.FAILED),
    ],
)
def test_maps_the_answer(account_file: Path, status: int, body: object, outcome: PushOutcome) -> None:
    assert _sender(account_file, _Google(status, body)).send(_DEVICE, _MESSAGE) is outcome


def test_an_unreadable_key_file_is_a_failure_not_a_crash(tmp_path: Path) -> None:
    google = _Google()
    sender = _sender(tmp_path / "missing.json", google)

    assert sender.send(_DEVICE, _MESSAGE) is PushOutcome.FAILED
    assert google.requests == []
