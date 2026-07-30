"""時刻の取り扱い。

保存・比較する時刻は常に UTC で、DB へは naive datetime として書く
（CLAUDE.md「ログ」参照）。tz 情報の有無が混ざると比較が例外になるため、
生成口をここ 1 か所に集約する。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """現在時刻を UTC の naive datetime で返す。"""
    return datetime.now(UTC).replace(tzinfo=None)


__all__ = ["utcnow"]
