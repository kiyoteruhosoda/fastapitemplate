from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription


class IPushSubscriptionRepository(ABC):
    @abstractmethod
    def save(self, subscription: PushSubscription) -> None:
        """登録する。同じ ``endpoint`` が既にあれば持ち主と鍵を書き換える。

        同じ端末で別の人がログインし直したときは、後の人の購読になる。
        """

    @abstractmethod
    def remove(self, user_id: int, endpoint: str) -> None:
        """本人の購読を外す（他人の ``endpoint`` は外さない）。"""

    @abstractmethod
    def remove_endpoint(self, endpoint: str) -> None:
        """通知サービスが「もう無い」と答えた購読を外す。"""

    @abstractmethod
    def for_users(self, user_ids: list[int]) -> list[PushSubscription]: ...

    @abstractmethod
    def exists(self, user_id: int, endpoint: str) -> bool: ...
