"""Sort order of the item list (value of the content setting ``item_list_order``; ADR-0085)."""

from __future__ import annotations

from enum import StrEnum


class ItemListOrder(StrEnum):
    #: Order added (oldest first)
    OLDEST = "oldest"
    #: Newest first
    NEWEST = "newest"
    #: By name
    NAME = "name"


__all__ = ["ItemListOrder"]
