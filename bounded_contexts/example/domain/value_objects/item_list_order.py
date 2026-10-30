"""アイテムの一覧の並び順（コンテンツ設定 ``item_list_order`` の値。ADR-0085）。"""

from __future__ import annotations

from enum import StrEnum


class ItemListOrder(StrEnum):
    #: 追加した順（古いものが先）
    OLDEST = "oldest"
    #: 新しいものが先
    NEWEST = "newest"
    #: 名前の順
    NAME = "name"


__all__ = ["ItemListOrder"]
