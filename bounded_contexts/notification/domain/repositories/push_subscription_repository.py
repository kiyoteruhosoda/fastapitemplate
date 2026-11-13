from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription


class IPushSubscriptionRepository(ABC):
    @abstractmethod
    def save(self, subscription: PushSubscription) -> None:
        """Register it. If the same ``endpoint`` already exists, overwrite its owner and keys.

        When someone else signs in again on the same device, the subscription becomes the later user's.
        """

    @abstractmethod
    def remove(self, user_id: int, endpoint: str) -> None:
        """Remove the user's own subscription (never another user's ``endpoint``)."""

    @abstractmethod
    def remove_endpoint(self, endpoint: str) -> None:
        """Remove a subscription the push service reported as gone."""

    @abstractmethod
    def for_users(self, user_ids: list[int]) -> list[PushSubscription]: ...

    @abstractmethod
    def exists(self, user_id: int, endpoint: str) -> bool: ...
