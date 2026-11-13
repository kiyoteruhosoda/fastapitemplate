"""Send device notifications via Web Push (VAPID) (ADR-0081 §3).

Encryption (RFC 8291) and the VAPID signature (RFC 8292) are left to ``pywebpush``.

⚠ **The private key is held by location, not value** (``WEB_PUSH_VAPID_PRIVATE_KEY_FILE``). Its content is
read from the file on each use. ⚠ **Changing the key breaks every existing subscription** (subscriptions are
bound to the public key). Devices get no notifications until users resubscribe in the UI.
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

#: How long the push service holds a notification while the device is off (seconds).
#: A notification older than a day is too late to show on the device (it is still in the bell).
_TTL_SECONDS = 24 * 60 * 60

#: Timeout per push service request (seconds).
_TIMEOUT_SECONDS = 10

#: Statuses with which the push service says the subscription is gone.
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
                # ⚠ Don't use ``Vapid.from_file``. If the file is missing it **silently creates a new key
                #   and writes it to that location**. If the write succeeds, it starts signing with a key that
                #   differs from the published public key and every subscription silently stops receiving.
                pem = Path(self._private_key_file).read_bytes()
                self._vapid = Vapid.from_pem(pem)
            except Exception:
                # The path is not secret, so it may be logged (it shows what to fix).
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
                # ⚠ pywebpush adds aud / exp to this dict. Reusing it would leave another push service's
                #   aud behind, so build it every time.
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
