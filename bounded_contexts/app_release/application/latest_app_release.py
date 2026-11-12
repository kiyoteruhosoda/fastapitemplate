"""Answer with the latest distributed release (ADR-0081 §4).

Devices ask every time the app is opened or brought to the foreground. Fetching from the
distribution store each time would hit the store once per device, and a slow store would drag
the asking devices down with it. The answer is cached in the process.

- A successful answer (including "none") is cached for :data:`ANSWER_TTL_SECONDS`. A new release
  is announced at most this long after it is built. Releases don't come out several times a day,
  so that is enough
- When the read fails, "nothing to announce" is cached for :data:`FAILURE_TTL_SECONDS` only, so
  devices are not kept waiting every time while the store is down
- ⚠ **Only one read in flight at a time.** A lock is held while reading so that devices arriving
  right as the cache expires don't all go to the store together
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from bounded_contexts.app_release.domain.app_release import (
    AppRelease,
    AppReleaseUnavailableError,
)
from bounded_contexts.app_release.domain.latest_release_source import LatestReleaseSource

logger = logging.getLogger(__name__)

ANSWER_TTL_SECONDS = 300.0
FAILURE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class _Remembered:
    release: AppRelease | None
    until: float


class LatestAppReleaseQuery:
    """Return the release the distribution store points to as latest (``None`` if unreadable).

    The source is **rebuilt from** ``source_factory`` **each time the cache expires**, so that when
    the settings are changed on the admin screen the next read goes to the new source without
    restarting the process.
    """

    def __init__(
        self,
        source_factory: Callable[[], LatestReleaseSource],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        answer_ttl_seconds: float = ANSWER_TTL_SECONDS,
        failure_ttl_seconds: float = FAILURE_TTL_SECONDS,
    ) -> None:
        self._source_factory = source_factory
        self._monotonic = monotonic
        self._answer_ttl_seconds = answer_ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds
        self._lock = threading.Lock()
        self._remembered: _Remembered | None = None

    def execute(self) -> AppRelease | None:
        with self._lock:
            now = self._monotonic()
            remembered = self._remembered
            if remembered is not None and now < remembered.until:
                return remembered.release

            try:
                release = self._source_factory().fetch()
                ttl = self._answer_ttl_seconds
            except AppReleaseUnavailableError as exc:
                # Tell the device "nothing to announce". Only the release notice is missing;
                # nothing else in the app is affected.
                logger.warning(
                    "app_release_unavailable",
                    extra={"event": "app_release.latest.unavailable", "reason": str(exc)},
                )
                release = None
                ttl = self._failure_ttl_seconds

            self._remembered = _Remembered(release=release, until=now + ttl)
            return release

    def forget(self) -> None:
        """Drop the cached answer (for tests, and for checking right after changing settings)."""
        with self._lock:
            self._remembered = None


__all__ = ["ANSWER_TTL_SECONDS", "FAILURE_TTL_SECONDS", "LatestAppReleaseQuery"]
