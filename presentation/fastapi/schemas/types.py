"""API スキーマで使う型。

`UtcDatetime` は保存値（naive な UTC）を、必ず ``Z`` で終わる ISO 文字列として
返すための注釈付き型。素の ``datetime`` のまま返すとオフセットが付かず、
ブラウザの ``new Date()`` がローカル時刻として読むため表示が 9 時間ずれる
（HANDOVER §14 / CLAUDE.md「時刻の契約」）。

レスポンスに時刻を足すときは ``datetime`` ではなくこの型を使う。
リクエスト側（絞り込み条件など）は素の ``datetime`` でよい。入力の tz は
``shared.kernel.timestamps.to_naive_utc()`` が吸収する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from shared.kernel.timestamps import isoformat_utc

UtcDatetime = Annotated[
    datetime,
    PlainSerializer(isoformat_utc, return_type=str, when_used="json"),
]

__all__ = ["UtcDatetime"]
