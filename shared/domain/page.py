"""One page of a list (ADR-0095). Requested with ``limit`` and ``offset``; returned with the total count."""

from __future__ import annotations

from dataclasses import dataclass

#: Page size when none is given
DEFAULT_PAGE_SIZE = 50
#: Upper limit returned at once. Larger requests are refused (rounding down would hide from the
#: caller that it got fewer than asked)
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class PageRequest:
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0


@dataclass(frozen=True)
class Page[T]:
    entries: list[T]
    #: The total count, not the count on this page
    total: int


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "Page", "PageRequest"]
