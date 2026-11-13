"""Answers the latest distributed version (ADR-0081 §4).

⚠ **A failing store does not drag devices down with it.** If it cannot be read, answer "nothing
to announce" and stay away from the store for a while. Answers that were read are cached too, so
not every device visit goes to the store.
"""

from __future__ import annotations

import logging

import pytest

from bounded_contexts.app_release.application.latest_app_release import LatestAppReleaseQuery
from bounded_contexts.app_release.domain.app_release import (
    AppRelease,
    AppReleaseUnavailableError,
)

_RELEASE = AppRelease(version="1.53.0", build=356, built_at=None)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Source:
    """Counts calls and returns a fixed answer (or exception)."""

    def __init__(self, answer: AppRelease | Exception | None) -> None:
        self.answer = answer
        self.calls = 0

    def fetch(self) -> AppRelease | None:
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _query(source: _Source, clock: _Clock) -> LatestAppReleaseQuery:
    return LatestAppReleaseQuery(
        lambda: source,
        monotonic=clock,
        answer_ttl_seconds=300,
        failure_ttl_seconds=60,
    )


def test_returns_what_the_source_names() -> None:
    source = _Source(_RELEASE)

    assert _query(source, _Clock()).execute() == _RELEASE


def test_an_answer_is_remembered_until_it_expires() -> None:
    source = _Source(_RELEASE)
    clock = _Clock()
    query = _query(source, clock)

    query.execute()
    clock.now += 299
    query.execute()
    assert source.calls == 1

    clock.now += 2
    query.execute()
    assert source.calls == 2


def test_nothing_configured_is_an_answer_too() -> None:
    """Also caches "not configured" (``None``). While unused, do not build the location every time."""
    source = _Source(None)
    clock = _Clock()
    query = _query(source, clock)

    assert query.execute() is None
    clock.now += 100
    assert query.execute() is None
    assert source.calls == 1


def test_an_unreadable_store_is_told_as_nothing_to_say(caplog: pytest.LogCaptureFixture) -> None:
    source = _Source(AppReleaseUnavailableError("garage is down"))

    with caplog.at_level(logging.WARNING):
        assert _query(source, _Clock()).execute() is None

    # Say nothing to the device, but leave a trace for operators.
    [record] = [r for r in caplog.records if r.getMessage() == "app_release_unavailable"]
    assert record.levelno == logging.WARNING
    assert record.__dict__["reason"] == "garage is down"


def test_a_failure_is_remembered_only_briefly() -> None:
    """While it is down, devices do not wait on every visit. But announce as soon as it recovers."""
    source = _Source(AppReleaseUnavailableError("garage is down"))
    clock = _Clock()
    query = _query(source, clock)

    query.execute()
    clock.now += 59
    query.execute()
    assert source.calls == 1

    source.answer = _RELEASE
    clock.now += 2
    assert query.execute() == _RELEASE
    assert source.calls == 2


def test_the_source_is_built_afresh_after_expiry() -> None:
    """A setting changed on screen applies from the next read, without recreating the process."""
    built: list[_Source] = []

    def factory() -> _Source:
        source = _Source(_RELEASE)
        built.append(source)
        return source

    clock = _Clock()
    query = LatestAppReleaseQuery(factory, monotonic=clock, answer_ttl_seconds=300)

    query.execute()
    clock.now += 301
    query.execute()

    assert len(built) == 2


def test_forget_drops_the_remembered_answer() -> None:
    source = _Source(_RELEASE)
    query = _query(source, _Clock())

    query.execute()
    query.forget()
    query.execute()

    assert source.calls == 2
