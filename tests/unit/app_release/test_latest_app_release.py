"""配布している最新版を答える（ADR-0048）。

⚠ **置き場が不調でも端末を道連れにしない。** 読めなければ「知らせることは無い」を
返し、しばらくは置き場へ行かない。読めた答えも覚えて、端末が来るたびに行かない。
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
    """呼ばれた回数を数え、決め打ちの答え（または例外）を返す。"""

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
    """設定が無い（``None``）も覚える。機能を使っていないあいだ、毎回読み先を組み立てない。"""
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

    # 端末には何も言わないが、運用には残す。
    [record] = [r for r in caplog.records if r.getMessage() == "app_release_unavailable"]
    assert record.levelno == logging.WARNING
    assert record.__dict__["reason"] == "garage is down"


def test_a_failure_is_remembered_only_briefly() -> None:
    """落ちているあいだ端末が来るたびに待たせない。ただし戻ったらすぐ知らせる。"""
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
    """設定を画面で変えたら、プロセスを作り直さなくても次の読みから新しい先へ行く。"""
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
