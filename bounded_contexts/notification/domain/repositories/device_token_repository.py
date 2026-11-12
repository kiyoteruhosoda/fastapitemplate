from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.entities.device_token import DeviceToken


class IDeviceTokenRepository(ABC):
    @abstractmethod
    def save(self, device: DeviceToken) -> None:
        """Register it. If the same token already exists, overwrite its owner.

        When someone else signs in again on the same device, the device becomes the later user's.
        """

    @abstractmethod
    def remove(self, user_id: int, token: str) -> None:
        """Remove the user's own device (never another user's token)."""

    @abstractmethod
    def remove_token(self, token: str) -> None:
        """Remove a token FCM reported as gone."""

    @abstractmethod
    def for_users(self, user_ids: list[int]) -> list[DeviceToken]: ...
