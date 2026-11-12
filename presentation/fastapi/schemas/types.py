"""Types used by the API schemas.

`UtcDatetime` is an annotated type that returns a stored value (naive UTC) as an ISO string
that always ends in ``Z``. A plain ``datetime`` is returned without an offset, and the
browser's ``new Date()`` reads it as local time, shifting the display by 9 hours
(HANDOVER §14 / CLAUDE.md "time contract").

When adding a time to a response, use this type instead of ``datetime``.
Requests (filter conditions etc.) may use plain ``datetime``; the input tz is
absorbed by ``shared.kernel.timestamps.to_naive_utc()``.
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
