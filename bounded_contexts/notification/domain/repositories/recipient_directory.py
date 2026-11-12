from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.value_objects.audience import Audience


class IRecipientDirectory(ABC):
    @abstractmethod
    def resolve(self, audience: Audience) -> list[int]:
        """Expand the audience into the IDs of the users to deliver to now (active users).

        Raises :class:`AudienceNotFoundError` if the group or user does not exist. Suspended users
        (``is_active`` false) receive nothing.
        """
