"""時刻の取り扱い。

保存・比較する時刻は常に UTC で、DB へは naive datetime として書く
（CLAUDE.md「ログ」参照）。tz 情報の有無が混ざると比較が例外になるため、
生成口と変換口をここ 1 か所に集約する。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """現在時刻を UTC の naive datetime で返す。"""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """外部から受け取った日時を、保存値と比較できる UTC naive へ揃える。

    ``2026-07-30T09:00:00+09:00`` のような tz 付きの入力は UTC へ変換してから
    tz を落とす。tz なしの入力は既に UTC として扱う（画面の表示も UTC のため）。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


__all__ = ["to_naive_utc", "utcnow"]
