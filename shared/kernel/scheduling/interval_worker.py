"""Resident thread that repeats the same job at a fixed interval.

Same shape as ``RestartWatcher`` in ``shared/kernel/restart`` (a daemon thread plus an ``Event``
for stopping), but that one looks for "has a request come in", while this one only looks at "has
the time come". It does not compare times, so it is not affected by clock skew between the
container and the DB.

**It knows nothing about the job itself.** The caller passes what to repeat (ADR-0075 §3).

Pass idempotent jobs only. Gunicorn runs several workers, so the same job runs at the same time
once per process. There is no mutual exclusion.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class IntervalWorker:
    """Thread that calls *job* every *interval_seconds*."""

    def __init__(self, name: str, job: Callable[[], None], interval_seconds: float) -> None:
        self._name = name
        self._job = job
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def name(self) -> str:
        return self._name

    def start(self) -> None:
        """Start the thread (calling it twice still runs only one)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        logger.info(
            "Started periodic job: name=%s interval=%ss",
            self._name,
            self._interval_seconds,
            extra={"event": "scheduling.worker.start"},
        )

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> None:
        """Run the job once. Never raises, even on failure.

        A single failure (a transient DB failure etc.) must not kill the thread. If it dies, every
        later interval silently stops and nobody notices until the process restarts.
        """
        try:
            self._job()
        except Exception:
            logger.warning(
                "Periodic job failed: name=%s",
                self._name,
                exc_info=True,
                extra={"event": "scheduling.worker.failed"},
            )

    def _run(self) -> None:
        # Run once right after startup. Even with a long interval, restarting the container runs
        # it immediately (no waiting for a full interval).
        self.run_once()
        while not self._stop_event.wait(self._interval_seconds):
            self.run_once()


__all__ = ["IntervalWorker"]
