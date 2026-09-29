from __future__ import annotations

from abc import ABC, abstractmethod

from bounded_contexts.notification.domain.value_objects.audience import Audience


class IRecipientDirectory(ABC):
    @abstractmethod
    def resolve(self, audience: Audience) -> list[int]:
        """宛先を、いま配る相手（有効な利用者）の ID へ展開する。

        グループ・利用者が無ければ :class:`AudienceNotFoundError`。止められた利用者
        （``is_active`` が偽）には配らない。
        """
