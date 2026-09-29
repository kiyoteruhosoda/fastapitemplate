"""端末への通知を Web Push（VAPID）で送る（ADR-0047）。

暗号化（RFC 8291）と VAPID の署名（RFC 8292）は ``pywebpush`` に任せる。

⚠ **秘密鍵は値ではなく場所で持つ**（``WEB_PUSH_VAPID_PRIVATE_KEY_FILE``）。中身は使うたびに
ファイルから読む。⚠ **鍵を替えると、いまある購読はすべて届かなくなる**（購読は公開鍵に
結び付いている）。利用者が画面で購読し直すまで端末への通知は出ない。
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription
from bounded_contexts.notification.domain.services.push_sender import PushMessage, PushOutcome, PushSender
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

#: 端末が電源を切っているあいだ、通知サービスに預けておく時間（秒）。
#: 1 日を過ぎたお知らせは端末に出しても遅い（ベルには残っている）。
_TTL_SECONDS = 24 * 60 * 60

#: 通知サービス 1 件あたりの待ち時間（秒）。
_TIMEOUT_SECONDS = 10

#: 通知サービスが「その購読はもう無い」と答える状態。
_GONE_STATUSES = frozenset({404, 410})


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class WebPushSender(PushSender):
    def __init__(self, private_key_file: str, subject: str) -> None:
        self._private_key_file = private_key_file
        self._subject = subject
        self._vapid: Vapid | None = None

    @classmethod
    def from_settings(cls) -> WebPushSender:
        return cls(settings.web_push_vapid_private_key_file, settings.web_push_subject)

    @property
    def enabled(self) -> bool:
        return bool(self._private_key_file and self._subject)

    def _load(self) -> Vapid | None:
        if not self.enabled:
            return None
        if self._vapid is None:
            try:
                # ⚠ ``Vapid.from_file`` を使わない。ファイルが無いと**黙って新しい鍵を作って
                #   その場所へ書き出す**。書けた場合は、配った公開鍵と違う鍵で署名し始め、
                #   すべての購読が静かに届かなくなる。
                pem = Path(self._private_key_file).read_bytes()
                self._vapid = Vapid.from_pem(pem)
            except Exception:
                # パスは秘密ではないので出してよい（どこを直せばよいかが分かる）。
                logger.warning(
                    "web_push_key_unreadable",
                    extra={"event": "notification.push.key_unreadable", "path": self._private_key_file},
                    exc_info=True,
                )
                return None
        return self._vapid

    def public_key(self) -> str | None:
        vapid = self._load()
        if vapid is None:
            return None
        raw: bytes = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return _b64url(raw)

    def send(self, subscription: PushSubscription, message: PushMessage) -> PushOutcome:
        vapid = self._load()
        if vapid is None:
            return PushOutcome.FAILED
        payload: dict[str, Any] = {
            "id": message.notification_id,
            "title": message.title,
            "body": message.body,
            "url": message.link_url,
        }
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=vapid,
                # ⚠ pywebpush はこの dict に aud / exp を書き足す。使い回すと別の通知サービスの
                #   aud が残るので、毎回作る。
                vapid_claims={"sub": self._subject},
                ttl=_TTL_SECONDS,
                timeout=_TIMEOUT_SECONDS,
            )
        except WebPushException as exc:
            if exc.status_code in _GONE_STATUSES:
                return PushOutcome.GONE
            logger.warning(
                "web_push_failed",
                extra={"event": "notification.push.failed", "status": exc.status_code},
            )
            return PushOutcome.FAILED
        except Exception:
            logger.warning("web_push_failed", extra={"event": "notification.push.failed"}, exc_info=True)
            return PushOutcome.FAILED
        return PushOutcome.DELIVERED


__all__ = ["WebPushSender"]
