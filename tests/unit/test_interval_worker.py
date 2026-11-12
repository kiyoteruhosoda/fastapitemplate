"""Interval worker thread (keeps running after failures, does not run during tests).

Each test uses its own thread name. A thread asked to stop takes a moment to actually go away,
and sharing a name would count the previous test's leftover.
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
    """Leave no threads started by the test."""
    yield
    stop_interval_workers()


def _live_threads_named(name: str) -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == name)


def test_run_once_calls_the_job() -> None:
    calls: list[int] = []

    IntervalWorker("worker-run-once", lambda: calls.append(1), 60.0).run_once()

    assert calls == [1]


def test_a_failing_job_does_not_escape() -> None:
    """One failure does not kill the thread (if it died, everything after would silently stop)."""

    def failing() -> None:
        raise RuntimeError("DB is temporarily down")

    IntervalWorker("worker-failing", failing, 60.0).run_once()


def test_the_thread_runs_the_job_right_after_starting() -> None:
    """Runs once without waiting for the interval (a restart runs it right away)."""
    ran = threading.Event()
    worker = IntervalWorker("worker-immediate", ran.set, 60.0)

    worker.start()
    try:
        assert ran.wait(timeout=5.0), "The run right after start did not happen"
    finally:
        worker.stop()


def test_starting_twice_keeps_a_single_thread() -> None:
    """Starting twice still runs only one thread (no duplicates within a process)."""
    name = "worker-started-twice"
    worker = IntervalWorker(name, lambda: None, 60.0)

    worker.start()
    worker.start()
    try:
        assert _live_threads_named(name) == 1
    finally:
        worker.stop()


def test_no_worker_starts_while_testing() -> None:
    """Under ``TESTING`` nothing is registered or started.

    A thread touching the DB without the test knowing writes to an engine that was already
    disposed, and another test fails.
    """
    name = "worker-under-testing"

    started = start_interval_worker(name, lambda: None, 60.0)

    assert started is None
    assert _live_threads_named(name) == 0
