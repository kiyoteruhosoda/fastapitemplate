from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping


class IContentSettingRepository(ABC):
    """Store of one tenant's content settings. The implementation takes the tenant in its constructor."""

    @abstractmethod
    def stored(self) -> Mapping[str, object]:
        """Saved values (key -> value)."""

    @abstractmethod
    def put(self, key: str, value: str | bool | int) -> None: ...

    @abstractmethod
    def remove(self, key: str) -> None: ...
