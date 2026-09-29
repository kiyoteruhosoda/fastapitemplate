"""スマホアプリへの通知を FCM（HTTP v1）で送る（ADR-0049）。

``firebase-admin`` は入れない。やることは 2 つだけで、どちらも既にある道具で足りる。

1. サービスアカウントの鍵で JWT を署名し（``pyjwt``）、Google の OAuth で
   アクセストークンに換える（``grant_type=jwt-bearer``。1 時間もつのでプロセスで覚える）
2. ``POST https://fcm.googleapis.com/v1/projects/<project>/messages:send``（``httpx``）

⚠ **鍵は値ではなく場所で持つ**（``FCM_SERVICE_ACCOUNT_FILE``）。Firebase のコンソールで
「新しい秘密鍵を生成」した JSON をそのまま置く。中身は送るたびに読む。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import jwt

from bounded_contexts.notification.domain.entities.device_token import DeviceToken
from bounded_contexts.notification.domain.services.push_sender import (
    DevicePushSender,
    PushMessage,
    PushOutcome,
)
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_TIMEOUT_SECONDS = 10
#: アクセストークンは 1 時間もつ。切れる少し前に取り直す。
_TOKEN_LIFETIME_SECONDS = 3600
_TOKEN_MARGIN_SECONDS = 300
#: FCM がこの答えを返したら、そのトークンはもう使えない（アプリを消した・データを消した）。
_GONE_ERROR_CODES = frozenset({"UNREGISTERED"})


class FcmUnavailableError(Exception):
    """鍵が読めない・Google の OAuth で断られた（送れない設定・状態）。"""


@dataclass(frozen=True)
class _ServiceAccount:
    project_id: str
    client_email: str
    private_key: str
    token_uri: str

    @classmethod
    def read(cls, path: str) -> _ServiceAccount:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(
                project_id=str(data["project_id"]),
                client_email=str(data["client_email"]),
                private_key=str(data["private_key"]),
                token_uri=str(data.get("token_uri") or _DEFAULT_TOKEN_URI),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # パスは秘密ではないので出してよい（どこを直せばよいかが分かる）。
            raise FcmUnavailableError(f"cannot read the service account file {path}: {type(exc).__name__}") from exc


class _AccessTokenCache:
    """Google のアクセストークンをプロセスで覚える（送るたびに OAuth へ行かない）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, float]] = {}

    def get(self, account: _ServiceAccount, client: httpx.Client) -> str:
        with self._lock:
            cached = self._tokens.get(account.client_email)
            now = time.time()
            if cached is not None and now < cached[1]:
                return cached[0]
            token = self._exchange(account, client, now)
            self._tokens[account.client_email] = (token, now + _TOKEN_LIFETIME_SECONDS - _TOKEN_MARGIN_SECONDS)
            return token

    def forget(self, account: _ServiceAccount) -> None:
        with self._lock:
            self._tokens.pop(account.client_email, None)

    @staticmethod
    def _exchange(account: _ServiceAccount, client: httpx.Client, now: float) -> str:
        assertion = jwt.encode(
            {
                "iss": account.client_email,
                "scope": _SCOPE,
                "aud": account.token_uri,
                "iat": int(now),
                "exp": int(now) + _TOKEN_LIFETIME_SECONDS,
            },
            account.private_key,
            algorithm="RS256",
        )
        try:
            response = client.post(
                account.token_uri,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            )
        except httpx.HTTPError as exc:
            raise FcmUnavailableError(f"cannot reach {account.token_uri}: {type(exc).__name__}") from exc
        if response.status_code != httpx.codes.OK:
            raise FcmUnavailableError(f"the token endpoint answered {response.status_code}")
        token = response.json().get("access_token")
        if not isinstance(token, str):
            raise FcmUnavailableError("the token endpoint returned no access_token")
        return token


_token_cache = _AccessTokenCache()


def _error_code(response: httpx.Response) -> str | None:
    """FCM の失敗の理由（``UNREGISTERED`` など）。``error.details[].errorCode`` に入っている。"""
    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        return None
    for detail in details if isinstance(details, list) else []:
        if isinstance(detail, dict) and isinstance(detail.get("errorCode"), str):
            return str(detail["errorCode"])
    return None


class FcmSender(DevicePushSender):
    def __init__(self, service_account_file: str, client: httpx.Client | None = None) -> None:
        self._service_account_file = service_account_file
        self._client = client

    @classmethod
    def from_settings(cls) -> FcmSender:
        return cls(settings.fcm_service_account_file)

    @property
    def enabled(self) -> bool:
        return bool(self._service_account_file)

    def send(self, device: DeviceToken, message: PushMessage) -> PushOutcome:
        if not self.enabled:
            return PushOutcome.FAILED
        client = self._client or httpx.Client(timeout=_TIMEOUT_SECONDS)
        try:
            account = _ServiceAccount.read(self._service_account_file)
            response = client.post(
                _SEND_URL.format(project=account.project_id),
                headers={"Authorization": f"Bearer {_token_cache.get(account, client)}"},
                json=self._payload(device, message),
            )
        except (FcmUnavailableError, httpx.HTTPError) as exc:
            logger.warning("fcm_unavailable", extra={"event": "notification.fcm.unavailable", "reason": str(exc)})
            return PushOutcome.FAILED
        finally:
            if self._client is None:
                client.close()
        return self._outcome(response, account)

    @staticmethod
    def _payload(device: DeviceToken, message: PushMessage) -> dict[str, Any]:
        # data の値は文字列しか許されない。アプリは notification_id で既読にし、url で行き先を開く。
        data = {"notification_id": str(message.notification_id)}
        if message.link_url:
            data["url"] = message.link_url
        return {
            "message": {
                "token": device.token,
                "notification": {"title": message.title, "body": message.body},
                "data": data,
                "android": {"priority": "high", "notification": {"tag": f"notification-{message.notification_id}"}},
            }
        }

    @staticmethod
    def _outcome(response: httpx.Response, account: _ServiceAccount) -> PushOutcome:
        if response.status_code == httpx.codes.OK:
            return PushOutcome.DELIVERED
        code = _error_code(response)
        if response.status_code == httpx.codes.NOT_FOUND or code in _GONE_ERROR_CODES:
            return PushOutcome.GONE
        if response.status_code == httpx.codes.UNAUTHORIZED:
            # 覚えていたアクセストークンが失効した（鍵を消された等）。次は取り直す。
            _token_cache.forget(account)
        logger.warning(
            "fcm_failed",
            extra={"event": "notification.fcm.failed", "status": response.status_code, "error_code": code},
        )
        return PushOutcome.FAILED


__all__ = ["FcmSender", "FcmUnavailableError"]
