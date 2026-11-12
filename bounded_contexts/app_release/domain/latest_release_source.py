"""Port for reading the latest release from the distribution store (ADR-0081 §4; implemented in Infrastructure)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.app_release.domain.app_release import AppRelease


class LatestReleaseSource(Protocol):
    def fetch(self) -> AppRelease | None:
        """Return the release the distribution store points to as latest.

        - ``None`` — nothing to read from is configured (the feature is not in use)
        - :class:`~bounded_contexts.app_release.domain.app_release.AppReleaseUnavailableError`
          — it is configured but could not be read
        """
        ...


__all__ = ["LatestReleaseSource"]
