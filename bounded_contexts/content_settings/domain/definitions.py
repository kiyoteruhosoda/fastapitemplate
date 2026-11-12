"""Definitions of the content setting items (ADR-0085 decision 1).

**This is the only place to add items.** The code holds each value's type, choices and default;
the DB holds only values a tenant changed. Derived apps delete the sample (``item_list_order``)
and list their own items.
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
    #: Allowed values for ``CHOICE`` (the display labels live in the UI dictionary)
    choices: tuple[str, ...] = ()
    #: Range for ``INTEGER`` (inclusive on both ends)
    minimum: int | None = None
    maximum: int | None = None


#: Sample: sort order of the item list (read by ``bounded_contexts/example``)
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
