"""一覧の 1 ページ（ADR-0095）。``limit`` と ``offset`` で指定し、全件数を添えて返す。"""

from __future__ import annotations

from dataclasses import dataclass

#: 指定が無いときの件数
DEFAULT_PAGE_SIZE = 50
#: 一度に返す上限。超える指定は断る（丸めると、頼んだより少ないことに呼ぶ側が気付けない）
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class PageRequest:
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0


@dataclass(frozen=True)
class Page[T]:
    entries: list[T]
    #: ページの件数ではなく、全体の件数
    total: int


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "Page", "PageRequest"]
