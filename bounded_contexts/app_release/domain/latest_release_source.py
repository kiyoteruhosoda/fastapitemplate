"""配布面から最新版を読む窓口（ADR-0048。実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.app_release.domain.app_release import AppRelease


class LatestReleaseSource(Protocol):
    def fetch(self) -> AppRelease | None:
        """配布面が最新として指している版を返す。

        - ``None`` —— 読む先が設定されていない（機能を使っていない）
        - :class:`~bounded_contexts.app_release.domain.app_release.AppReleaseUnavailableError`
          —— 設定はあるのに読めなかった
        """
        ...


__all__ = ["LatestReleaseSource"]
