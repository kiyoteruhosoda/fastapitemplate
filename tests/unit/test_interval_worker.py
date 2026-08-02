"""定期実行スレッド（失敗しても止まらないこと・テスト中は動かないこと）。

スレッド名はテストごとに変える。停止を要求したスレッドが実際に消えるまでには
わずかな間があり、名前を共有すると前のテストの残りを数えてしまうため。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from shared.kernel.scheduling import (
    IntervalWorker,
    start_interval_worker,
    stop_interval_workers,
)


@pytest.fixture(autouse=True)
def _stop_workers() -> Iterator[None]:
    """テストが起こしたスレッドを残さない。"""
    yield
    stop_interval_workers()


def _live_threads_named(name: str) -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == name)


def test_run_once_calls_the_job() -> None:
    calls: list[int] = []

    IntervalWorker("worker-run-once", lambda: calls.append(1), 60.0).run_once()

    assert calls == [1]


def test_a_failing_job_does_not_escape() -> None:
    """1 回の失敗でスレッドを死なせないこと（死ぬと以降が黙って止まる）。"""

    def failing() -> None:
        raise RuntimeError("DB が一時的に落ちている")

    IntervalWorker("worker-failing", failing, 60.0).run_once()


def test_the_thread_runs_the_job_right_after_starting() -> None:
    """間隔を待たずに 1 回走ること（起動し直せばすぐ実行できる）。"""
    ran = threading.Event()
    worker = IntervalWorker("worker-immediate", ran.set, 60.0)

    worker.start()
    try:
        assert ran.wait(timeout=5.0), "起動直後の 1 回が走っていない"
    finally:
        worker.stop()


def test_starting_twice_keeps_a_single_thread() -> None:
    """二重に開始しても 1 本だけ動くこと（プロセス内で重複させない）。"""
    name = "worker-started-twice"
    worker = IntervalWorker(name, lambda: None, 60.0)

    worker.start()
    worker.start()
    try:
        assert _live_threads_named(name) == 1
    finally:
        worker.stop()


def test_no_worker_starts_while_testing() -> None:
    """``TESTING`` のときは登録も起動もしないこと。

    テストが知らないうちに DB を触るスレッドが走ると、後始末したエンジンへ
    書きに行って別のテストが落ちる。
    """
    name = "worker-under-testing"

    started = start_interval_worker(name, lambda: None, 60.0)

    assert started is None
    assert _live_threads_named(name) == 0
