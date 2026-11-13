"""Entry point for periodic execution.

Use it to run "a job repeated at a fixed interval" inside the process. No scheduler library is
added (the requirements are within what can be met without more dependencies; ADR-0075 §3).

Callers use only this module's public names::

    start_interval_worker("log-retention", purge_expired_logs_once, 6 * 3600)
    ...
    stop_interval_workers()
"""

from __future__ import annotations

from collections.abc import Callable

from shared.kernel.scheduling.interval_worker import IntervalWorker

_workers: dict[str, IntervalWorker] = {}


def start_interval_worker(name: str, job: Callable[[], None], interval_seconds: float) -> IntervalWorker | None:
    """Start periodic execution of *name* (returns the running one if it already exists).

    Does nothing during tests (``TESTING``), so tests do not unknowingly run threads that touch
    the DB.
    """
    from shared.kernel.settings.settings import settings

    if settings.testing:
        return None

    existing = _workers.get(name)
    if existing is not None:
        return existing

    worker = IntervalWorker(name, job, interval_seconds)
    worker.start()
    _workers[name] = worker
    return worker


def stop_interval_workers() -> None:
    """Stop the started threads (on process exit and for test cleanup)."""
    for worker in _workers.values():
        worker.stop()
    _workers.clear()


__all__ = ["IntervalWorker", "start_interval_worker", "stop_interval_workers"]
