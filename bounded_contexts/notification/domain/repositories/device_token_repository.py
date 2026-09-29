from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.entities.device_token import DeviceToken


class IDeviceTokenRepository(ABC):
    @abstractmethod
    def save(self, device: DeviceToken) -> None:
        """登録する。同じトークンが既にあれば持ち主を書き換える。

        同じ端末で別の人がサインインし直したときは、後の人の端末になる。
        """

    @abstractmethod
    def remove(self, user_id: int, token: str) -> None:
        """本人の端末を外す（他人のトークンは外さない）。"""

    @abstractmethod
    def remove_token(self, token: str) -> None:
        """FCM が「もう無い」と答えたトークンを外す。"""

    @abstractmethod
    def for_users(self, user_ids: list[int]) -> list[DeviceToken]: ...
