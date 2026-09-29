"""端末への通知を送る窓口（ADR-0047。実装は Infrastructure 層）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription


class PushOutcome(StrEnum):
    DELIVERED = "delivered"
    #: 通知サービスが「その購読はもう無い」と答えた（404 / 410）。購読を外す。
    GONE = "gone"
    #: それ以外の失敗。購読は残す（通知サービスの一時的な不調かもしれない）。
    FAILED = "failed"


@dataclass(frozen=True)
class PushMessage:
    """端末に渡す中身。Service Worker がこれを読んで通知を出す。"""

    notification_id: int
    title: str
    body: str
    link_url: str | None


class PushSender(ABC):
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """送れる設定になっているか（鍵が無ければ偽）。"""

    @abstractmethod
    def public_key(self) -> str | None:
        """ブラウザの購読に渡す公開鍵（base64url）。送れない設定なら ``None``。"""

    @abstractmethod
    def send(self, subscription: PushSubscription, message: PushMessage) -> PushOutcome: ...
