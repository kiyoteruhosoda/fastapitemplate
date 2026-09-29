"""配布している最新版を答える（ADR-0048）。

端末はアプリを開くたび・前面に戻るたびに聞いてくる。そのたびに配布面へ
取りに行くと、端末の数だけ置き場を叩くことになるうえ、置き場が遅いと
聞いてきた端末を道連れにする。答えはプロセスの中で覚えておく。

- 読めた答え（「無い」を含む）は :data:`ANSWER_TTL_SECONDS` 覚える。新しい版は
  焼いてから最大この時間遅れて知らされる。版は日に何度も出ないので十分
- 読めなかったときは :data:`FAILURE_TTL_SECONDS` だけ「知らせることは無い」を
  覚える。置き場が落ちているあいだ、端末が来るたびに待たされない
- ⚠ **読みに行くのは同時に 1 本だけ。** 覚えが切れた瞬間に来た端末が揃って
  置き場へ行かないよう、読みに行くあいだは鍵を持つ
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
    """配布面が最新として指している版を返す（読めなければ ``None``）。

    読む先は ``source_factory`` で**覚えが切れるたびに作り直す**。設定を管理画面で
    変えたとき、プロセスを作り直さなくても次の読みから新しい先へ行くため。
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
                # 端末には「知らせることは無い」と返す。版の知らせが出ないだけで、
                # アプリのほかの機能には何も響かないため。
                logger.warning(
                    "app_release_unavailable",
                    extra={"event": "app_release.latest.unavailable", "reason": str(exc)},
                )
                release = None
                ttl = self._failure_ttl_seconds

            self._remembered = _Remembered(release=release, until=now + ttl)
            return release

    def forget(self) -> None:
        """覚えている答えを捨てる（テストと、設定を変えた直後に確かめたいとき用）。"""
        with self._lock:
            self._remembered = None


__all__ = ["ANSWER_TTL_SECONDS", "FAILURE_TTL_SECONDS", "LatestAppReleaseQuery"]
