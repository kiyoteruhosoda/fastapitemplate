from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping


class IContentSettingRepository(ABC):
    """1 つのテナントのコンテンツ設定の置き場。テナントは実装のコンストラクタで受け取る。"""

    @abstractmethod
    def stored(self) -> Mapping[str, object]:
        """保存してある値（キー → 値）。"""

    @abstractmethod
    def put(self, key: str, value: str | bool | int) -> None: ...

    @abstractmethod
    def remove(self, key: str) -> None: ...
