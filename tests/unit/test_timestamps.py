"""Time boundaries.

Contract (HANDOVER §14): store and compare in UTC; only the screen converts to local time. If an
ISO string returned by the server lacks ``Z``, the browser's ``new Date()`` reads it as local
time, shifting the display by 9 hours for JST viewers. This pins that values leaving the boundary
always end in ``Z``.
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


def test_utc_datetime_field_renders_with_a_trailing_z() -> None:
    """Times in response models also come out with Z (so the frontend's new Date reads them correctly)."""
    from pydantic import BaseModel

    from presentation.fastapi.schemas.types import UtcDatetime

    class _Sample(BaseModel):
        updated_at: UtcDatetime

    dumped = _Sample(updated_at=datetime(2026, 8, 26, 4, 20, 47)).model_dump(mode="json")
    assert dumped["updated_at"] == "2026-08-26T04:20:47Z"
