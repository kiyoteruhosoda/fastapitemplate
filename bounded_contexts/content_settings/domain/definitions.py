"""コンテンツ設定の項目の定義（ADR-0085 決定 1）。

**項目を足すのはここだけ。** 値の型・選べる値・既定値をコードで持ち、DB はテナントが
変えた値しか持たない。派生アプリは見本（``item_list_order``）を消して自分の項目を並べる。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContentSettingType(StrEnum):
    CHOICE = "choice"
    BOOLEAN = "boolean"
    INTEGER = "integer"


@dataclass(frozen=True)
class ContentSettingDefinition:
    key: str
    value_type: ContentSettingType
    default: str | bool | int
    #: ``CHOICE`` で選べる値（表示の文言は画面の辞書が持つ）
    choices: tuple[str, ...] = ()
    #: ``INTEGER`` の範囲（両端を含む）
    minimum: int | None = None
    maximum: int | None = None


#: 見本。アイテムの一覧の並び順（``bounded_contexts/example`` が読む）
ITEM_LIST_ORDER = ContentSettingDefinition(
    key="item_list_order",
    value_type=ContentSettingType.CHOICE,
    default="oldest",
    choices=("oldest", "newest", "name"),
)

CONTENT_SETTINGS: tuple[ContentSettingDefinition, ...] = (ITEM_LIST_ORDER,)


__all__ = [
    "CONTENT_SETTINGS",
    "ITEM_LIST_ORDER",
    "ContentSettingDefinition",
    "ContentSettingType",
]
