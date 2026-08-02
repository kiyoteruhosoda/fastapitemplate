"""定期実行スレッド（失敗しても止まらないこと・テスト中は動かないこと）。"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from shared.kernel.scheduling import (
    IntervalWorker,
    start_interval_worker,
    stop_interval_workers,
)

_WORKER_NAME = "test-interval-worker"


@pytest.fixture(autouse=True)
def _stop_workers() -> Iterator[None]:
    """テストが起こしたスレッドを残さない。"""
    yield
    stop_interval_workers()


def _live_worker_threads() -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == _WORKER_NAME)


def test_run_once_calls_the_job() -> None:
    calls: list[int] = []

    IntervalWorker(_WORKER_NAME, lambda: calls.append(1), 60.0).run_once()

    assert calls == [1]


def test_a_failing_job_does_not_escape() -> None:
    """1 回の失敗でスレッドを死なせないこと（死ぬと以降が黙って止まる）。"""

    def failing() -> None:
        raise RuntimeError("DB が一時的に落ちている")

    IntervalWorker(_WORKER_NAME, failing, 60.0).run_once()


def test_the_thread_runs_the_job_right_after_starting() -> None:
    """間隔を待たずに 1 回走ること（起動し直せばすぐ実行できる）。"""
    ran = threading.Event()
    worker = IntervalWorker(_WORKER_NAME, ran.set, 60.0)

    worker.start()
    try:
        assert ran.wait(timeout=5.0), "起動直後の 1 回が走っていない"
    finally:
        worker.stop()


def test_starting_twice_keeps_a_single_thread() -> None:
    """二重に開始しても 1 本だけ動くこと（プロセス内で重複させない）。"""
    worker = IntervalWorker(_WORKER_NAME, lambda: None, 60.0)

    worker.start()
    worker.start()
    try:
        assert _live_worker_threads() == 1
    finally:
        worker.stop()


def test_no_worker_starts_while_testing() -> None:
    """``TESTING`` のときは登録も起動もしないこと。

    テストが知らないうちに DB を触るスレッドが走ると、後始末したエンジンへ
    書きに行って別のテストが落ちる。
    """
    started = start_interval_worker(_WORKER_NAME, lambda: None, 60.0)

    assert started is None
    assert _live_worker_threads() == 0
