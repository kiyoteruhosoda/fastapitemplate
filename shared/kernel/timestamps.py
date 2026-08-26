"""時刻の取り扱い。

保存・比較する時刻は常に UTC で、DB へは naive datetime として書く
（CLAUDE.md「ログ」参照）。tz 情報の有無が混ざると比較が例外になるため、
生成口と変換口をここ 1 か所に集約する。

画面に出す時刻をローカルタイムへ直すのはフロントエンドの仕事で、サーバは UTC の
まま返す。ただし **API の外へ出す文字列には必ず ``Z`` を付ける**（``isoformat_utc``）。
オフセットの無い ISO 文字列は JavaScript の ``new Date()`` がローカル時刻として
解釈するため、付け忘れると画面が 9 時間ずれる。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """現在時刻を UTC の naive datetime で返す。"""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """外部から受け取った日時を、保存値と比較できる UTC naive へ揃える。

    ``2026-07-30T09:00:00+09:00`` のような tz 付きの入力は UTC へ変換してから
    tz を落とす。tz なしの入力は既に UTC として扱う（保存値が UTC naive のため）。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def isoformat_utc(value: datetime) -> str:
    """API の外へ出す ISO 文字列。末尾は必ず ``Z`` になる。

    naive な値は UTC とみなす（保存値が UTC naive のため）。``Z`` の無い
    ISO 文字列はブラウザがローカル時刻として読むので、境界を出る値は必ず
    ここを通す。
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


__all__ = ["isoformat_utc", "to_naive_utc", "utcnow"]
