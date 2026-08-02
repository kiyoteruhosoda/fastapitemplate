"""一定間隔で同じ仕事を繰り返す常駐スレッド。

``shared/kernel/restart`` の ``RestartWatcher`` と同じ形（daemon スレッド + 停止用の
``Event``）だが、あちらは「要求が来たか」を見るためのもので、こちらは「時間が来たか」
だけを見る。時刻の比較をしないので、コンテナと DB の時計のずれに影響されない。

**仕事の中身は知らない。** 何を繰り返すかは呼び出し側が渡す（ADR-0021）。

冪等な仕事だけを渡すこと。Gunicorn は複数ワーカーで動くため、同じ仕事が同時刻に
プロセスの数だけ走る。排他の仕組みは持たない。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class IntervalWorker:
    """*interval_seconds* ごとに *job* を呼ぶスレッド。"""

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
        """スレッドを開始する（二重に呼んでも 1 つだけ動く）。"""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        logger.info(
            "定期処理を開始しました: name=%s interval=%ss",
            self._name,
            self._interval_seconds,
            extra={"event": "scheduling.worker.start"},
        )

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> None:
        """仕事を 1 回実行する。失敗しても例外を投げない。

        1 回の失敗（DB の一時障害など）でスレッドを死なせない。死ぬと次の間隔以降が
        黙って止まり、プロセスを再起動するまで誰も気付けない。
        """
        try:
            self._job()
        except Exception:
            logger.warning(
                "定期処理に失敗しました: name=%s",
                self._name,
                exc_info=True,
                extra={"event": "scheduling.worker.failed"},
            )

    def _run(self) -> None:
        # 起動直後に 1 回走らせる。長い間隔にしても、コンテナを起動し直せば
        # すぐ実行できる（間隔の分だけ待たされない）。
        self.run_once()
        while not self._stop_event.wait(self._interval_seconds):
            self.run_once()


__all__ = ["IntervalWorker"]
