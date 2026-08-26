"""時刻の境界。

契約（HANDOVER §14）: 保存・比較は UTC、ローカルタイムへ直すのは画面だけ。
サーバが返す ISO 文字列に ``Z`` が無いと、ブラウザの ``new Date()`` はそれを
ローカル時刻として読む。JST の閲覧者では表示が 9 時間ずれるので、境界を出る
値が必ず ``Z`` で終わることをここで固定する。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from shared.kernel.timestamps import isoformat_utc, to_naive_utc, utcnow

JST = timezone(timedelta(hours=9))


def test_utcnow_returns_naive_utc() -> None:
    now = utcnow()
    assert now.tzinfo is None
    assert abs((now - datetime.now(UTC).replace(tzinfo=None)).total_seconds()) < 5


def test_naive_stored_value_gets_a_trailing_z() -> None:
    assert isoformat_utc(datetime(2026, 8, 26, 4, 20, 47)) == "2026-08-26T04:20:47Z"


def test_aware_value_is_converted_to_utc_before_rendering() -> None:
    assert isoformat_utc(datetime(2026, 8, 26, 13, 20, 47, tzinfo=JST)) == "2026-08-26T04:20:47Z"


def test_offset_notation_is_never_emitted() -> None:
    for value in (
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=JST),
    ):
        rendered = isoformat_utc(value)
        assert rendered.endswith("Z"), rendered
        assert "+" not in rendered, rendered


def test_to_naive_utc_drops_the_offset_after_converting() -> None:
    assert to_naive_utc(datetime(2026, 8, 26, 13, 0, tzinfo=JST)) == datetime(2026, 8, 26, 4, 0)
    assert to_naive_utc(None) is None
