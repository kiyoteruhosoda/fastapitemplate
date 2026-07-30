"""``LogPage`` の不変条件と、外部入力の丸め方。"""

from __future__ import annotations

import pytest

from bounded_contexts.audit.domain.value_objects.log_page import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    LogPage,
)


def test_defaults_to_the_first_page() -> None:
    page = LogPage()
    assert (page.limit, page.offset) == (DEFAULT_LIMIT, 0)


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (-1, 0), (MAX_LIMIT + 1, 0), (DEFAULT_LIMIT, -1)])
def test_rejects_values_outside_the_allowed_range(limit: int, offset: int) -> None:
    with pytest.raises(ValueError, match=r"limit|offset"):
        LogPage(limit=limit, offset=offset)


@pytest.mark.parametrize(
    ("limit", "expected"),
    [(None, DEFAULT_LIMIT), (0, DEFAULT_LIMIT), (-5, DEFAULT_LIMIT), (10, 10), (MAX_LIMIT + 100, MAX_LIMIT)],
)
def test_of_clamps_the_limit(limit: int | None, expected: int) -> None:
    assert LogPage.of(limit=limit).limit == expected


@pytest.mark.parametrize(("offset", "expected"), [(None, 0), (-5, 0), (20, 20)])
def test_of_clamps_the_offset(offset: int | None, expected: int) -> None:
    assert LogPage.of(offset=offset).offset == expected
