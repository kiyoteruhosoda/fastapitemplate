"""ログ検索のページ指定（新しい順に ``limit`` 件、``offset`` 件目から）。

過大な取得で DB と画面を詰まらせないため、上限をここで強制する。境界の判断を
各エンドポイントに散らさないための値オブジェクト。
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@dataclass(frozen=True)
class LogPage:
    """1 ページの取得範囲。常に ``1 <= limit <= MAX_LIMIT`` かつ ``offset >= 0``。"""

    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError(f"limit は 1〜{MAX_LIMIT} の範囲でなければならない: {self.limit}")
        if self.offset < 0:
            raise ValueError(f"offset は 0 以上でなければならない: {self.offset}")

    @classmethod
    def of(cls, limit: int | None = None, offset: int | None = None) -> LogPage:
        """未指定・範囲外の値を既定値へ丸めて生成する（外部入力の受け口）。"""
        clamped_limit = DEFAULT_LIMIT if limit is None or limit < 1 else min(limit, MAX_LIMIT)
        return cls(limit=clamped_limit, offset=max(offset or 0, 0))


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "LogPage"]
