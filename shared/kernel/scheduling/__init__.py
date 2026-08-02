"""定期実行の入口。

プロセスの中で「一定間隔で繰り返す仕事」を動かしたいときに使う。スケジューラの
ライブラリは足していない（依存を増やさずに済む範囲の要求しかないため。ADR-0021）。

呼び出し側はこのモジュールの公開名だけを使う::

    start_interval_worker("log-retention", purge_expired_logs_once, 6 * 3600)
    ...
    stop_interval_workers()
"""

from __future__ import annotations

from collections.abc import Callable

from shared.kernel.scheduling.interval_worker import IntervalWorker

_workers: dict[str, IntervalWorker] = {}


def start_interval_worker(name: str, job: Callable[[], None], interval_seconds: float) -> IntervalWorker | None:
    """*name* の定期実行を開始する（既に動いていればそれを返す）。

    テスト実行時（``TESTING``）は何もしない。テストが知らないうちに DB を触る
    スレッドを走らせないため。
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
    """起動済みのスレッドを止める（プロセス終了時・テスト後始末用）。"""
    for worker in _workers.values():
        worker.stop()
    _workers.clear()


__all__ = ["IntervalWorker", "start_interval_worker", "stop_interval_workers"]
